import httpx
import pytest

import xducraft_pig_bot as pig_bot


@pytest.mark.asyncio
async def test_fetch_all_images_uses_current_pighub_contract(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://www.pighub.top/api/images?sort=0"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "OK",
                "data": [
                    {
                        "id": 651,
                        "title": "？！",
                        "filename": "？！.jpg",
                        "image_url": "/images/？！.jpg",
                    },
                    "invalid item",
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(pig_bot.httpx, "AsyncClient", lambda **_kwargs: client)

    images = await pig_bot.fetch_all_images()

    assert images == [
        {
            "id": "651",
            "title": "？！",
            "filename": "？！.jpg",
            "url": "https://www.pighub.top/images/%EF%BC%9F%EF%BC%81.jpg",
        }
    ]


def test_build_image_url_escapes_filename_path_characters():
    assert (
        pig_bot.build_image_url("/images/+1猪#1.jpg")
        == "https://www.pighub.top/images/%2B1%E7%8C%AA%231.jpg"
    )
