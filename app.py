from dashboard import create_app

app = create_app()
server = app.server  # required for Render/gunicorn

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8050))
    app.run(debug=False, host="0.0.0.0", port=port)