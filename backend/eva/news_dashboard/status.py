from .models import NewsStatus
def get_news_dashboard_status() -> NewsStatus:
    return NewsStatus(True, "mock_fixture", False, "local/mock dashboard ready; live RSS view available (eva news live)", "Phase 28 Coding Specialist / CodingAgent")
