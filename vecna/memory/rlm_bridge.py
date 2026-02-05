"""
RLM Bridge: Docker-based Recursive Language Model for near-infinite memory.

This module provides:
1. Docker container management for isolated Python REPL
2. Prewarmed REPL for fast sub-query execution
3. Recursive retrieval for deep memory exploration
4. Direct PostgreSQL queries for substrate access

The RLM pattern allows Vecna to recursively query its own memory,
decomposing complex questions into sub-queries that are executed
in a sandboxed environment.

PostgreSQL Connection:
The RLM container connects directly to PostgreSQL using the VECNA_PG_URL
environment variable passed at container startup.
"""

import os
import json
import asyncio
import subprocess
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("vecna.rlm_bridge")


@dataclass
class RLMConfig:
    """Configuration for the RLM bridge."""

    # Docker image to use (needs psycopg2 installed)
    image: str = "python:3.11-slim"

    # Container name prefix
    container_prefix: str = "vecna-rlm"

    # Timeout for REPL operations (seconds)
    timeout: int = 30

    # Max recursion depth for sub-queries
    max_recursion: int = 3

    # Memory limit for container
    memory_limit: str = "512m"

    # Whether to persist container between queries
    persist_container: bool = True

    # PostgreSQL connection URL (passed to container as env var)
    pg_url: Optional[str] = None


@dataclass
class RLMResult:
    """Result from an RLM query."""

    query: str
    answer: str
    sub_queries: List[str] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    depth: int = 0
    execution_time_ms: float = 0
    success: bool = True
    error: Optional[str] = None


class DockerNotAvailableError(Exception):
    """Raised when Docker is not available."""

    pass


class RLMBridge:
    """
    Bridge to Docker-based RLM for recursive memory retrieval.

    This enables near-infinite memory by offloading complex retrieval
    to a sandboxed Python environment that can recursively query
    the hive's substrate via PostgreSQL.
    """

    def __init__(self, config: Optional[RLMConfig] = None):
        self.config = config or RLMConfig()
        self._container_id: Optional[str] = None
        self._docker_available: Optional[bool] = None
        self._prewarmed: bool = False
        self._packages_installed: bool = False

        # Get PG URL from config or environment
        if self.config.pg_url is None:
            self.config.pg_url = os.environ.get("VECNA_PG_URL")

    def is_docker_available(self) -> bool:
        """Check if Docker is available on the system."""
        if self._docker_available is not None:
            return self._docker_available

        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
            )
            self._docker_available = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._docker_available = False

        return self._docker_available

    async def prewarm(self) -> bool:
        """
        Prewarm the Docker REPL container.

        This starts a container in the background that can be reused
        for fast query execution. Non-blocking.

        Returns True if prewarm succeeded.
        """
        if not self.is_docker_available():
            logger.warning("Docker not available, RLM bridge disabled")
            return False

        if self._prewarmed and self._container_id:
            return True

        try:
            # Start container in detached mode with PG URL env var
            container_name = f"{self.config.container_prefix}-{os.getpid()}"

            cmd = [
                "docker",
                "run",
                "-d",
                "--name",
                container_name,
                "--memory",
                self.config.memory_limit,
            ]

            # Pass PostgreSQL URL as environment variable
            if self.config.pg_url:
                cmd.extend(["-e", f"VECNA_PG_URL={self.config.pg_url}"])

            cmd.extend(
                [
                    self.config.image,
                    "python",
                    "-c",
                    "import time; time.sleep(3600)",  # Keep alive for 1 hour
                ]
            )

            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                self._container_id = stdout.decode().strip()
                self._prewarmed = True
                logger.info(f"RLM container prewarmed: {self._container_id[:12]}")

                # Install psycopg2-binary for PostgreSQL access
                success, _ = await self.install_packages(["psycopg2-binary"])
                if success:
                    self._packages_installed = True
                else:
                    logger.warning("Failed to install psycopg2-binary in RLM container")

                return True
            else:
                logger.error(f"Failed to prewarm RLM container: {stderr.decode()}")
                return False

        except Exception as e:
            logger.error(f"Error prewarming RLM container: {e}")
            return False

    async def execute_code(self, code: str) -> Tuple[str, str, int]:
        """
        Execute Python code in the RLM container.

        Returns (stdout, stderr, return_code).
        """
        if not self._container_id:
            # Try to prewarm first
            if not await self.prewarm():
                raise DockerNotAvailableError("RLM container not available")

        try:
            cmd = ["docker", "exec", self._container_id, "python", "-c", code]

            result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=self.config.timeout,
            )
            stdout, stderr = await result.communicate()

            return stdout.decode(), stderr.decode(), result.returncode or 0

        except asyncio.TimeoutError:
            return "", "Execution timed out", -1
        except Exception as e:
            return "", str(e), -1

    async def install_packages(self, packages: List[str]) -> Tuple[bool, str]:
        """
        Install Python packages via pip in the RLM container.

        Args:
            packages: List of package names to install

        Returns:
            (success, output) tuple
        """
        if not packages:
            return True, ""

        if not self._container_id:
            if not await self.prewarm():
                raise DockerNotAvailableError("RLM container not available")

        try:
            # Install packages using pip
            cmd = [
                "docker",
                "exec",
                self._container_id,
                "pip",
                "install",
                "--quiet",
                "--disable-pip-version-check",
                *packages,
            ]

            logger.info(f"Installing packages in container: {packages}")

            result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=120,  # 2 minute timeout for package installation
            )
            stdout, stderr = await result.communicate()

            output = stdout.decode() + stderr.decode()

            if result.returncode == 0:
                logger.info(f"Successfully installed packages: {packages}")
                return True, output
            else:
                logger.error(f"Failed to install packages: {output}")
                return False, output

        except asyncio.TimeoutError:
            return False, "Package installation timed out (120s limit)"
        except Exception as e:
            return False, str(e)

    async def recursive_query(
        self,
        query: str,
        depth: int = 0,
    ) -> RLMResult:
        """
        Execute a recursive query against the substrate via PostgreSQL.

        This is the core RLM pattern:
        1. Decompose query into sub-queries
        2. Execute each sub-query against PostgreSQL
        3. Aggregate evidence
        4. Generate answer
        """
        start_time = datetime.now()

        if depth >= self.config.max_recursion:
            return RLMResult(
                query=query,
                answer="Max recursion depth reached",
                depth=depth,
                success=False,
                error="Max recursion depth",
            )

        # Check if PG URL is available
        if not self.config.pg_url:
            return RLMResult(
                query=query,
                answer="PostgreSQL connection not configured",
                depth=depth,
                success=False,
                error="VECNA_PG_URL not set",
            )

        # Generate retrieval code that queries PostgreSQL directly
        retrieval_code = f'''
import json
import os

try:
    import psycopg2
except ImportError:
    print(json.dumps({{"error": "psycopg2 not installed"}}))
    exit(1)

# Get connection string from environment
pg_url = os.environ.get("VECNA_PG_URL")
if not pg_url:
    print(json.dumps({{"error": "VECNA_PG_URL not set"}}))
    exit(1)

try:
    conn = psycopg2.connect(pg_url)
    cur = conn.cursor()
    
    query = """{query}"""
    query_words = query.lower().split()
    
    results = []
    
    # Search hive_state table for substrate
    cur.execute("SELECT state FROM hive_state WHERE key = 'default'")
    row = cur.fetchone()
    
    if row:
        state = row[0]  # JSONB is auto-parsed
        
        # Search facts
        for fact in state.get("facts", []):
            fact_words = set(fact["content"].lower().split())
            overlap = len(set(query_words) & fact_words)
            if overlap > 0:
                score = overlap / len(set(query_words) | fact_words)
                results.append({{
                    "type": "fact",
                    "content": fact["content"],
                    "score": score,
                    "confidence": fact.get("confidence", 0.5)
                }})
        
        # Search beliefs
        for belief in state.get("beliefs", []):
            belief_words = set(belief["content"].lower().split())
            overlap = len(set(query_words) & belief_words)
            if overlap > 0:
                score = overlap / len(set(query_words) | belief_words)
                results.append({{
                    "type": "belief",
                    "content": belief["content"],
                    "score": score,
                    "confidence": belief.get("confidence", 0.5)
                }})
        
        # Search hypotheses
        for hyp in state.get("hypotheses", []):
            hyp_words = set(hyp["content"].lower().split())
            overlap = len(set(query_words) & hyp_words)
            if overlap > 0:
                score = overlap / len(set(query_words) | hyp_words)
                results.append({{
                    "type": "hypothesis",
                    "content": hyp["content"],
                    "score": score,
                    "confidence": hyp.get("confidence", 0.5)
                }})
    
    # Also search memory_items table if it exists
    try:
        cur.execute("""
            SELECT item_type, content, confidence 
            FROM memory_items 
            WHERE content ILIKE %s
            LIMIT 20
        """, (f"%{{query[:50]}}%",))
        
        for row in cur.fetchall():
            item_type, content, confidence = row
            results.append({{
                "type": item_type,
                "content": content,
                "score": 0.5,  # Simple match score
                "confidence": confidence or 0.5
            }})
    except Exception:
        pass  # Table might not exist
    
    # Sort by score and take top 10
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:10]
    
    cur.close()
    conn.close()
    
    print(json.dumps({{"query": query, "results": results, "success": True}}))
    
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
'''

        stdout, stderr, code = await self.execute_code(retrieval_code)

        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        if code != 0:
            return RLMResult(
                query=query,
                answer="",
                depth=depth,
                execution_time_ms=execution_time,
                success=False,
                error=stderr,
            )

        try:
            result_data = json.loads(stdout)

            if "error" in result_data:
                return RLMResult(
                    query=query,
                    answer="",
                    depth=depth,
                    execution_time_ms=execution_time,
                    success=False,
                    error=result_data["error"],
                )

            evidence = result_data.get("results", [])

            # Build answer from evidence
            if evidence:
                answer_parts = [f"Found {len(evidence)} relevant items:"]
                for item in evidence[:5]:
                    answer_parts.append(
                        f"- [{item['type']}][{item['confidence']:.1f}] {item['content']}"
                    )
                answer = "\n".join(answer_parts)
            else:
                answer = "No relevant evidence found in substrate."

            return RLMResult(
                query=query,
                answer=answer,
                evidence=evidence,
                depth=depth,
                execution_time_ms=execution_time,
                success=True,
            )

        except json.JSONDecodeError:
            return RLMResult(
                query=query,
                answer=stdout,
                depth=depth,
                execution_time_ms=execution_time,
                success=True,
            )

    async def shutdown(self) -> None:
        """Stop and remove the RLM container."""
        if self._container_id:
            try:
                subprocess.run(
                    ["docker", "rm", "-f", self._container_id],
                    capture_output=True,
                    timeout=10,
                )
                logger.info(f"RLM container stopped: {self._container_id[:12]}")
            except Exception as e:
                logger.error(f"Error stopping RLM container: {e}")
            finally:
                self._container_id = None
                self._prewarmed = False
                self._packages_installed = False

    def __del__(self):
        """Cleanup on deletion."""
        if self._container_id and not self.config.persist_container:
            try:
                subprocess.run(
                    ["docker", "rm", "-f", self._container_id],
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass


# Singleton instance for the bridge
_rlm_bridge: Optional[RLMBridge] = None


def get_rlm_bridge(config: Optional[RLMConfig] = None) -> RLMBridge:
    """Get or create the singleton RLM bridge."""
    global _rlm_bridge
    if _rlm_bridge is None:
        _rlm_bridge = RLMBridge(config)
    return _rlm_bridge


async def prewarm_rlm() -> bool:
    """Prewarm the RLM bridge (convenience function)."""
    bridge = get_rlm_bridge()
    return await bridge.prewarm()


async def rlm_query(query: str) -> RLMResult:
    """Execute an RLM query (convenience function)."""
    bridge = get_rlm_bridge()
    return await bridge.recursive_query(query)
