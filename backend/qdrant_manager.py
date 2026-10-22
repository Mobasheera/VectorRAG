from qdrant_client import QdrantClient

from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct
)

from .config import (
    QDRANT_URL,
    QDRANT_COLLECTION,
    TOP_K_QDRANT
)

from .embeddings import (
    get_embedding_dimension
)


class QdrantManager:

    def __init__(self):

        self.client = QdrantClient(
            url=QDRANT_URL
        )

        self.collection_name = (
            QDRANT_COLLECTION
        )

        self._create_collection()


    # =====================================================
    # COLLECTION
    # =====================================================

    def _create_collection(self):

        existing = [

            collection.name

            for collection

            in self.client.get_collections().collections

        ]


        if (
            self.collection_name
            not in existing
        ):

            dimension = (
                get_embedding_dimension()
            )

            self.client.create_collection(

                collection_name=
                    self.collection_name,

                vectors_config=
                    VectorParams(

                        size=dimension,

                        distance=
                            Distance.COSINE

                    )

            )

            print(
                "Created Qdrant collection:",
                self.collection_name
            )


    # =====================================================
    # INSERT / UPSERT
    # =====================================================

    def upsert_documents(
        self,
        documents
    ):

        if not documents:

            return 0


        points = []


        for document in documents:

            points.append(

                PointStruct(

                    id=document["id"],

                    vector=document["vector"],

                    payload={

                        "text":
                            document["text"],

                        "url":
                            document["url"],

                        "title":
                            document["title"],

                        "domain":
                            document["domain"],

                        "trust_score":
                            document["trust_score"],

                        "source_type":
                            document["source_type"]

                    }

                )

            )


        self.client.upsert(

            collection_name=
                self.collection_name,

            points=points,

            wait=True

        )


        return len(points)


    # =====================================================
    # SEARCH
    # =====================================================

    def search(
        self,
        vector,
        limit=None
    ):

        if limit is None:

            limit = TOP_K_QDRANT


        response = self.client.query_points(

            collection_name=
                self.collection_name,

            query=vector,

            limit=limit,

            with_payload=True

        )


        return response.points


    # =====================================================
    # COUNT
    # =====================================================

    def count(self):

        result = self.client.count(

            collection_name=
                self.collection_name,

            exact=True

        )


        return result.count


# =========================================================
# GLOBAL MANAGER
# =========================================================

qdrant_manager = QdrantManager()