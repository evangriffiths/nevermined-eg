import modal
from fastapi import Response

image = modal.Image.debian_slim().pip_install("requests")
app = modal.App(name="example", image=image)

BASIC_SERVICE_CHARGE = 1
PREMIUM_SERVICE_CHARGE = 10


@app.function()
@modal.web_endpoint(docs=True)
def test(name: str = "World") -> Response:
    credits_consumed = (
        BASIC_SERVICE_CHARGE if name == "World" else PREMIUM_SERVICE_CHARGE
    )
    headers = {"NVMCreditsConsumed": str(credits_consumed)}
    content = f"Hello {name}"
    return Response(content=content, headers=headers, media_type="application/json")
