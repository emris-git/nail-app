from app.domain.price_list import ParsedService, PriceListParseResult, validate_price_list_result


def test_valid_price_list():
    data = {
        "raw_text": "Маникюр - 1500",
        "services": [{"name": "Маникюр", "price": 1500, "duration_minutes": 60}],
    }
    result = validate_price_list_result(data)
    assert isinstance(result, PriceListParseResult)
    assert result.services[0].name == "Маникюр"


def test_reject_empty_services():
    data = {"raw_text": "", "services": []}
    try:
        validate_price_list_result(data)
    except ValueError:
        return
    assert False, "Expected ValueError for empty services"

