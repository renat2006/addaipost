from flask import Flask

app = Flask(__name__)


@app.route('/')
def hello_world():
    from datetime import datetime
    print(datetime.now())

    return 'Hello World!'


if __name__ == '__main__':
    app.run()
