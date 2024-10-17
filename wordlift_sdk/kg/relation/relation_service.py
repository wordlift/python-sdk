import wordlift_client
from wordlift_client import Configuration, VectorSearchQueriesApi, VectorSearchQueryRequest

from wordlift_sdk.kg import Entity


class RelationService:
    _configuration: Configuration

    def __init__(self, configuration: Configuration):
        self._configuration = configuration

    def get_relations(self, entity: Entity):
        async with wordlift_client.ApiClient(self._configuration) as api_client:
            # Search for related pages
            search_api = VectorSearchQueriesApi(api_client)

            related_request = VectorSearchQueryRequest(
                query_url=entity_url,
                similarity_top_k=100,
                fields=["schema:url", "schema:headline", "ex-private:category", "ex-private:subCategory",
                        "ex-private:subSubCategory", "ex-private:subSubSubCategory", "ex-private:location",
                        "ex-private:pagesSection"]
            )

            try:
                related_page = await search_api.create_query(vector_search_query_request=related_request)
                print(f"Number of related items found: {len(related_page.items)}")
            except Exception as e:
                logger.error(f"Error during vector search: {e}")
                return False

            # Filter and re-rank results
            filtered_results = []
            for item in related_page.items:
                item_url = safe_get_field(item, "schema:url")
                if item_url == entity_url:
                    print(f"Skipping original entity: {item_url}")
                    continue

                item_category = safe_get_field(item, "ex-private:category")
                item_sub_category = safe_get_field(item, "ex-private:subCategory")
                item_sub_sub_category = safe_get_field(item, "ex-private:subSubCategory")
                item_sub_sub_sub_category = safe_get_field(item, "ex-private:subSubSubCategory")

                print(f"Processing item: {item_url}")
                print(
                    f"Item categories: {item_category} > {item_sub_category} > {item_sub_sub_category} > {item_sub_sub_sub_category}")

                if (item_category == main_category or
                        item_sub_category == sub_category or
                        item_sub_sub_category == sub_sub_category or
                        item_sub_sub_sub_category == sub_sub_sub_category):

                    score = item.score
                    item_location = safe_get_field(item, "ex-private:location")
                    item_pages_section = safe_get_field(item, "ex-private:pagesSection")

                    print(f"Item location: {item_location}")
                    print(f"Item pages section: {item_pages_section}")

                    if item_location == location:
                        score += 0.2
                        print("Location match, score boosted")
                    if item_pages_section == "Top":
                        score += 0.1
                        print("Top page, score boosted")

                    filtered_results.append({
                        "url": item_url,
                        "headline": safe_get_field(item, "schema:headline"),
                        "score": score
                    })
                    print(f"Item added to filtered results. Score: {score}")
                else:
                    print("Item categories don't match any of our category levels, skipped")

                print("---")
