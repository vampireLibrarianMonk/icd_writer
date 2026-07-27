"""OpenSearch index management and document indexing.

Handles index creation, mapping, bulk indexing, and deletion.
Supports both local Docker OpenSearch and AWS OpenSearch Service.
"""

from __future__ import annotations

import logging
from typing import Any

from opensearchpy import OpenSearch, RequestsHttpConnection, helpers
from requests_aws4auth import AWS4Auth
import boto3

from .config import IndexConfig, SearchConfig, SimilarityMetric
from .chunking import Chunk

logger = logging.getLogger(__name__)


class IndexManager:
    """Manages OpenSearch indices for ICD search."""

    def __init__(self, search_config: SearchConfig) -> None:
        self.config = search_config
        self._client: OpenSearch | None = None

    @property
    def client(self) -> OpenSearch:
        """Lazily connect to OpenSearch."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> OpenSearch:
        """Create OpenSearch client (local or AWS managed)."""
        if self.config.opensearch_domain:
            # AWS OpenSearch Service — use IAM auth
            credentials = boto3.Session().get_credentials()
            auth = AWS4Auth(
                credentials.access_key,
                credentials.secret_key,
                self.config.aws_region,
                "es",
                session_token=credentials.token,
            )
            return OpenSearch(
                hosts=[{
                    "host": self.config.opensearch_domain,
                    "port": 443,
                }],
                http_auth=auth,
                use_ssl=True,
                verify_certs=True,
                connection_class=RequestsHttpConnection,
            )
        else:
            # Local Docker — no auth (security plugin disabled)
            return OpenSearch(
                hosts=[{
                    "host": self.config.opensearch_host,
                    "port": self.config.opensearch_port,
                }],
                use_ssl=False,
                verify_certs=False,
            )

    def create_index(self, index_config: IndexConfig) -> str:
        """Create an OpenSearch index with kNN mapping.

        Returns the index name.
        """
        index_name = index_config.index_name
        dims = index_config.embedding_config.dimensions
        metric = index_config.similarity_metric.value

        # Map similarity metric to OpenSearch space_type
        space_type_map = {
            SimilarityMetric.COSINE.value: "cosinesimil",
            SimilarityMetric.L2.value: "l2",
            SimilarityMetric.INNER_PRODUCT.value: "innerproduct",
        }
        space_type = space_type_map.get(metric, "cosinesimil")

        body = {
            "settings": {
                "index": {
                    "knn": True,
                    "knn.algo_param.ef_search": 256,
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                },
            },
            "mappings": {
                "properties": {
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": dims,
                        "method": {
                            "name": "hnsw",
                            "space_type": space_type,
                            "engine": "nmslib",
                            "parameters": {
                                "ef_construction": index_config.ef_construction,
                                "m": index_config.m,
                            },
                        },
                    },
                    "text": {"type": "text", "analyzer": "standard"},
                    "chunk_id": {"type": "keyword"},
                    "document_hash": {"type": "keyword"},
                    "document_title": {"type": "text"},
                    "page_number": {"type": "integer"},
                    "section_heading": {"type": "text"},
                    "section_number": {"type": "keyword"},
                    "content_type": {"type": "keyword"},
                    "metadata": {"type": "object", "enabled": False},
                },
            },
        }

        if self.client.indices.exists(index=index_name):
            logger.info(f"Index {index_name} already exists, skipping creation")
        else:
            self.client.indices.create(index=index_name, body=body)
            logger.info(f"Created index {index_name} ({dims}d, {space_type})")

        return index_name

    def delete_index(self, index_config: IndexConfig) -> None:
        """Delete an index."""
        index_name = index_config.index_name
        if self.client.indices.exists(index=index_name):
            self.client.indices.delete(index=index_name)
            logger.info(f"Deleted index {index_name}")

    def index_chunks(self, index_name: str, chunks: list[Chunk],
                     embeddings: list[list[float]]) -> int:
        """Bulk index chunks with their embeddings.

        Returns number of successfully indexed documents.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunk count ({len(chunks)}) != embedding count ({len(embeddings)})"
            )

        actions = []
        for chunk, vector in zip(chunks, embeddings):
            doc = {
                "_index": index_name,
                "_id": chunk.chunk_id,
                "_source": {
                    "embedding": vector,
                    "text": chunk.text,
                    "chunk_id": chunk.chunk_id,
                    "document_hash": chunk.document_hash,
                    "document_title": chunk.document_title,
                    "page_number": chunk.page_number,
                    "section_heading": chunk.section_heading,
                    "section_number": chunk.section_number,
                    "content_type": chunk.content_type,
                    "metadata": chunk.metadata,
                },
            }
            actions.append(doc)

        success, errors = helpers.bulk(self.client, actions, raise_on_error=False)
        if errors:
            logger.warning(f"Bulk index had {len(errors)} errors")
            for err in errors[:5]:
                logger.warning(f"  {err}")
        logger.info(f"Indexed {success}/{len(chunks)} chunks into {index_name}")
        return success

    def delete_document(self, index_name: str, document_hash: str) -> int:
        """Remove all chunks for a document (for re-indexing)."""
        response = self.client.delete_by_query(
            index=index_name,
            body={
                "query": {
                    "term": {"document_hash": document_hash},
                },
            },
        )
        deleted = response.get("deleted", 0)
        logger.info(f"Deleted {deleted} chunks for {document_hash} from {index_name}")
        return deleted

    def get_index_stats(self, index_name: str) -> dict[str, Any]:
        """Get index statistics."""
        stats = self.client.indices.stats(index=index_name)
        idx_stats = stats["indices"].get(index_name, {}).get("primaries", {})
        return {
            "index_name": index_name,
            "doc_count": idx_stats.get("docs", {}).get("count", 0),
            "size_bytes": idx_stats.get("store", {}).get("size_in_bytes", 0),
        }

    def list_indices(self) -> list[str]:
        """List all ICD-related indices."""
        indices = self.client.indices.get_alias(index="icd-*")
        return list(indices.keys())
