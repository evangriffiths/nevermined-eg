import modal
from fastapi import Response

image = modal.Image.debian_slim().pip_install("requests")
app = modal.App(name="example", image=image)


@app.function()
@modal.web_endpoint(docs=True)
def test(name: str = "World") -> Response:
    credits_consumed = 1 if name == "World" else 10
    headers = {"NVMCreditsConsumed": str(credits_consumed)}
    content = f"Hello {name}"
    return Response(content=content, headers=headers, media_type="application/json")
