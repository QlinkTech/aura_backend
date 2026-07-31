import uuid

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from onereside_chatbot.constants import TEXT_EMBEDDING_MODEL
from onereside_chatbot.utils.env_load import chorma_tenant, chroma_api, openai_api_key
from onereside_chatbot.utils.logger_config import logger


embedding_fn = OpenAIEmbeddingFunction(
    api_key=openai_api_key,
    model_name=TEXT_EMBEDDING_MODEL
)


def _get_collections():
    """Create a fresh ChromaDB client per operation — eliminates stale connection issues."""
    client = chromadb.CloudClient(
        tenant=chorma_tenant,
        database="OneReside",
        api_key=chroma_api
    )
    product_col = client.get_collection(name="product", embedding_function=embedding_fn)
    brand_col = client.get_collection(name="brands", embedding_function=embedding_fn)
    return product_col, brand_col


def generate_id():
    """Generate a short unique ID."""
    return f"{uuid.uuid4().hex[:8]}"


def build_search_text(product: dict) -> str:
    """Build a rich text blob for embedding from multiple product fields."""
    def labeled(label: str, values: list) -> str:
        joined = ", ".join(values)
        return f"{label}: {joined}" if joined else ""

    parts = [
        product.get("name") or "",
        f"Category: {product['category']}" if product.get("category") else "",
        f"Type: {product['type']}" if product.get("type") else "",
        f"Size: {product['size']}" if product.get("size") else "",
        product.get("description") or "",
        labeled("Style tags", product.get("style_tags") or []),
        labeled("Materials", product.get("materials") or []),
        labeled("Ideal for", product.get("ideal_for") or []),
        labeled("Colors available", product.get("colors_available") or []),
        labeled("Deliverables", product.get("deliverables") or []),
    ]
    return " ; ".join(p for p in parts if p)


def add_product(product: dict):
    """Add a product to the vector collection using a rich text embedding."""
    product_id = product["product_id"]
    brand_id = product["brand_id"]
    category = product["category"]
    try:
        product_col, _ = _get_collections()
        product_col.add(
            ids=[product_id],
            documents=[build_search_text(product)],
            metadatas=[{"brand_id": brand_id, "category": category, "product_id": product_id}]
        )
        logger.info("Product added to vector DB.", extra={"product_id": product_id, "brand_id": brand_id})
    except Exception as e:
        logger.error("Error adding product to vector DB.", extra={"product_id": product_id, "error": e})
        raise e


def semantic_search(query: str, brand_ids: list = None, exclude_ids: list = None, n_results: int = 3, listing_type: str = None, product_type: str = None):
    """
    Search products by semantic similarity.
    Pass brand_ids to scope to specific brands; omit (or pass None) to search all brands.
    Pass listing_type to filter by product/service.
    Pass product_type to filter by ready_product/made_to_order.
    Returns list of matching product IDs.
    """
    try:
        product_col, _ = _get_collections()
        filters = []
        if brand_ids:
            filters.append({"brand_id": {"$in": brand_ids}})
        if listing_type:
            filters.append({"listing_type": {"$eq": listing_type}})
        if product_type:
            filters.append({"type": {"$eq": product_type}})
        where_clause = {"$and": filters} if len(filters) > 1 else (filters[0] if filters else None)
        response = product_col.query(query_texts=[query], where=where_clause, n_results=n_results)

        product_ids = []
        if response and response.get("ids"):
            for pid in response["ids"][0]:
                if exclude_ids and pid in exclude_ids:
                    continue
                product_ids.append(pid)

        logger.info("Semantic search completed.", extra={"query": query, "brand_ids": brand_ids, "results": product_ids})
        return product_ids
    except Exception as e:
        logger.error("Error during semantic search.", extra={"query": query, "brand_ids": brand_ids, "error": e})
        raise e


def update_product_embedding(product: dict):
    """Update a product's embedding in the vector DB using the full product data."""
    product_id = product["product_id"]
    try:
        product_col, _ = _get_collections()
        product_col.upsert(
            ids=[product_id],
            documents=[build_search_text(product)],
            metadatas=[{"brand_id": product.get("brand_id", ""), "category": product.get("category", ""), "product_id": product_id}]
        )
        logger.info("Product embedding updated in vector DB.", extra={"product_id": product_id})
    except Exception as e:
        logger.error("Error updating product embedding in vector DB.", extra={"product_id": product_id, "error": e})
        raise e


def delete_brand_products(brand_id: str):
    """Delete all product vectors for a brand."""
    try:
        product_col, _ = _get_collections()
        product_col.delete(where={"brand_id": brand_id})
        logger.info("Deleted brand products from vector DB.", extra={"brand_id": brand_id})
    except Exception as e:
        logger.error("Error deleting brand products from vector DB.", extra={"brand_id": brand_id, "error": e})
        raise e


def delete_product(product_id: str):
    """Delete a single product from vector DB."""
    try:
        product_col, _ = _get_collections()
        product_col.delete(ids=[product_id])
        logger.info("Deleted product from vector DB.", extra={"product_id": product_id})
    except Exception as e:
        logger.error("Error deleting product from vector DB.", extra={"product_id": product_id, "error": e})
        raise e


def _build_brand_text(brand: dict) -> str:
    """Build embedding text from brand fields."""
    def labeled(label: str, values: list) -> str:
        joined = ", ".join(values)
        return f"{label}: {joined}" if joined else ""

    parts = [
        brand.get("brand_name", ""),
        brand.get("brand_description", ""),
        labeled("Categories offered", brand.get("categories_offered", [])),
    ]
    return " ; ".join(p for p in parts if p)


def add_brand(brand: dict):
    """Add a brand to the brands vector collection."""
    brand_id = brand["brand_id"]
    try:
        _, brand_col = _get_collections()
        brand_col.add(
            ids=[brand_id],
            documents=[_build_brand_text(brand)],
            metadatas=[{
                "brand_id": brand_id,
                "brand_name": brand.get("brand_name", ""),
                "categories_offered": ", ".join(brand.get("categories_offered", [])),
                "has_ready_products": brand.get("has_ready_products", False),
                "has_custom_products": brand.get("has_custom_products", False),
                "has_services": brand.get("has_services", False),
            }]
        )
        logger.info("Brand added to vector DB.", extra={"brand_id": brand_id})
    except Exception as e:
        logger.error("Error adding brand to vector DB.", extra={"brand_id": brand_id, "error": e})
        raise e


def update_brand_embedding(brand: dict):
    """Update a brand's embedding in the vector DB."""
    brand_id = brand["brand_id"]
    try:
        _, brand_col = _get_collections()
        brand_col.update(
            ids=[brand_id],
            documents=[_build_brand_text(brand)],
            metadatas=[{
                "brand_id": brand_id,
                "brand_name": brand.get("brand_name", ""),
                "categories_offered": ", ".join(brand.get("categories_offered", [])),
                "has_ready_products": brand.get("has_ready_products", False),
                "has_custom_products": brand.get("has_custom_products", False),
                "has_services": brand.get("has_services", False),
            }]
        )
        logger.info("Brand embedding updated in vector DB.", extra={"brand_id": brand_id})
    except Exception as e:
        logger.error("Error updating brand embedding in vector DB.", extra={"brand_id": brand_id, "error": e})
        raise e


def delete_brand(brand_id: str):
    """Delete a brand from the brands vector collection."""
    try:
        _, brand_col = _get_collections()
        brand_col.delete(ids=[brand_id])
        logger.info("Deleted brand from vector DB.", extra={"brand_id": brand_id})
    except Exception as e:
        logger.error("Error deleting brand from vector DB.", extra={"brand_id": brand_id, "error": e})
        raise e


def semantic_brand_search(query: str, n_results: int = 5, where: dict = None) -> list[dict]:
    """
    Semantic search over the brands collection.
    Pass `where` to filter by Chroma metadata (e.g. {"has_services": {"$eq": True}}).
    Returns a list of dicts with metadata + the embedded document text.
    """
    try:
        _, brand_col = _get_collections()
        response = brand_col.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["metadatas", "documents"],
        )
        results = []
        metadatas = response.get("metadatas", [[]])[0]
        documents = response.get("documents", [[]])[0]
        for meta, doc in zip(metadatas, documents):
            results.append({**meta, "search_text": doc})
        logger.info("Brand semantic search completed.", extra={"query": query, "where": where, "results": results})
        return results
    except Exception as e:
        logger.error("Error during brand semantic search.", extra={"query": query, "error": e})
        raise e
