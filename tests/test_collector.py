from __future__ import annotations

from douhot_crawler import collector


class FakeRows:
    @property
    def first(self):
        return self

    async def wait_for(self, **_kwargs):
        return None

    async def count(self):
        return 5

    def nth(self, index):
        return index


class FakePage:
    def locator(self, selector):
        assert selector == "tbody tr"
        return FakeRows()


async def test_collection_stops_after_requested_number_of_new_videos(monkeypatch):
    persisted = []

    async def extract_record(*, row, **_kwargs):
        return {"title": f"title-{row}", "author_name": f"author-{row}"}

    async def capture_detail(*, record, row_number, **_kwargs):
        return {**record, "video_id": str(row_number), "top_comments": ""}

    async def persist_page(records, page_number):
        persisted.append((page_number, list(records)))

    monkeypatch.setattr(collector, "extract_video_list_record", extract_record)
    monkeypatch.setattr(collector, "capture_video_detail", capture_detail)

    result = await collector.collect_all_video_details(
        FakePage(),
        set(),
        0,
        persist_page,
        lambda: False,
        max_results=2,
    )

    assert result == (2, 0, False)
    assert len(persisted) == 1
    assert [record["video_id"] for record in persisted[0][1]] == ["1", "2"]
