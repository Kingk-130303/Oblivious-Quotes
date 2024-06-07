from flask import Flask, render_template, jsonify, Response, request, url_for, redirect, session
from bson import json_util
import requests
import json
import re,os
from os import environ as env
from urllib.parse import quote_plus,urlencode
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv,find_dotenv
from authlib.integrations.flask_client import OAuth

USER_INFO_URL = f'https://{env.get("AUTH0_DOMAIN")}/userinfo'

ENV_FILE = find_dotenv()
if ENV_FILE:
    load_dotenv(ENV_FILE)


def get_user_info(access_token):
  headers = {"Authorization": f"Bearer {access_token}"}
  response = requests.get(USER_INFO_URL, headers=headers)
  if response.status_code == 200:
    return response.json()
  else:
    # print(f"Error fetching user info: {response.status_code}")
    return None


app = Flask(__name__,static_url_path='/static')
app.secret_key = env.get("APP_SECRET_KEY")

oauth = OAuth(app)
oauth.register(
    "auth0",
    client_id=env.get("AUTH0_CLIENT_ID"),
    client_secret=env.get("AUTH0_CLIENT_SECRET"),
    client_kwargs={
        "scope": "openid profile email",
    },
    server_metadata_url=f'https://{env.get("AUTH0_DOMAIN")}/.well-known/openid-configuration'
)

@app.route("/login")
def login():
    return oauth.auth0.authorize_redirect(
        redirect_uri=url_for("callback", _external=True)
    )


@app.route("/callback", methods=["GET", "POST"])
def callback():
    token = oauth.auth0.authorize_access_token()
    # print(token)
    session["user"] = token
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(
        "https://" + env.get("AUTH0_DOMAIN")
        + "/v2/logout?"
        + urlencode(
            {
                "returnTo": url_for("home", _external=True),
                "client_id": env.get("AUTH0_CLIENT_ID"),
            },
            quote_via=quote_plus,
        )
    )
print("Before ENV")
mongo_uri = os.getenv('MONGO_URI')
print(mongo_uri)
if mongo_uri is None:
    raise ValueError("MONGO_URI environment variable is not set")

client = MongoClient(mongo_uri, server_api=ServerApi('1'))

db = client.get_database('Quotes')


quotes_collection = db.quotes

quotes_collection.create_index("a")



@app.route("/")
def home():
    user_info = None
    if 'user' in session:
        user_info = get_user_info(session['user']['access_token'])
        print(user_info)
        return render_template("user.html", user_info_available=user_info is not None, user_info=user_info)
    else:
        # Redirect to login page if user is not logged in
        return render_template("homepage.html")


def normalize_author_name(name):
    return re.sub(r'\W+', ' ', name).lower()


@app.route("/addToMyQuotes", methods=["POST"])
def add_to_my_quotes():
    user_id = get_user_info(session['user']['access_token'])  # Get the unique user ID
    quote = request.json.get("quote")
    author = request.json.get("author")

    if not quote or not author:
        return jsonify({"error": "Quote and author are required"}), 400

    user_quotes_collection = db.userQuotes
    user_quotes_collection.insert_one({
        "user_id": user_id['sub'],
        "quote": quote,
        "author": author
    })

    return jsonify({"message": "Quote added to your collection"}), 200

@app.route('/myQuotes')
def my_quotes_page():
    user_info = get_user_info(session['user']['access_token'])
    return render_template("myquotes.html", user_info=user_info)

@app.route("/removeQuote", methods=["POST"])
def remove_quote():
    user_id = request.json.get("user_id")
    quote_text = request.json.get("quote")

    if not user_id or not quote_text:
        return jsonify({"error": "User ID and quote text are required"}), 400

    user_quotes_collection = db.userQuotes
    result = user_quotes_collection.delete_one({"user_id": user_id, "quote": quote_text})

    if result.deleted_count == 1:
        return jsonify({"message": "Quote removed successfully"}), 200
    else:
        return jsonify({"error": "Quote not found or could not be removed"}), 404


@app.route("/FetchmyQuotes")
def my_quotes():
    user_id = get_user_info(session['user']['access_token'])  # Get the unique user ID
    user_quotes_collection = db.userQuotes
    quotes = user_quotes_collection.find({"user_id": user_id['sub']})
    return Response(json_util.dumps(quotes), mimetype='application/json')


@app.route("/getQuote")
def quote():
    api_url = "https://zenquotes.io/api/quotes/"
    response = requests.get(api_url)
    data = response.json()
    for quote in data:
        existing_quote = quotes_collection.find_one({"q": quote["q"]})
        if existing_quote is None:
            quotes_collection.insert_one(quote)

    return Response(json.dumps(data, default=json_util.default), mimetype='application/json')



@app.route("/searchByAuthor", methods=['GET'])
def search_by_author():
    author_name = request.args.get('author')
    if author_name:
        normalized_author_name = normalize_author_name(author_name)

        quotes = quotes_collection.find({"a": {"$regex": re.compile(normalized_author_name, re.IGNORECASE)}})
        
        return Response(json_util.dumps(quotes), mimetype='application/json')
    else:
        return jsonify({"error": "Author name is required"}), 400

if __name__ == "__main__":
    app.run(debug=True,ssl_context='adhoc')