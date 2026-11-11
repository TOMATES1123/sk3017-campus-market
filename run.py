"""开发环境启动入口。

生产环境请使用 waitress / gunicorn：
    waitress-serve --listen=0.0.0.0:5000 run:app
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # debug 由环境变量控制，避免部署时误开调试模式
    import os

    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="127.0.0.1", port=5000, debug=debug)
