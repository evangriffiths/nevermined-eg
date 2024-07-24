import modal

image = modal.Image.debian_slim().pip_install("requests")
app = modal.App(name="example", image=image)


@app.function()
@modal.web_endpoint(docs=True)
def test(name: str = "World") -> str:
    return f"Hello {name}"
