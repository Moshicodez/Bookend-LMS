from flask import Flask, render_template, request

app = Flask(
    __name__,
    template_folder="frontend/templates",
    static_folder="frontend/static",
)


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    preview_message = None
    if request.method == "POST":
        preview_message = "Sign-in is not connected yet. This page is a frontend preview."
    return render_template("auth/login.html", preview_message=preview_message)


if __name__ == "__main__":
    app.run(debug=True)
