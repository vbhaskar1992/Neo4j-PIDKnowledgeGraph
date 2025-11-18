

import os
import json
import re
from flask import Flask, request, jsonify
from neo4j import GraphDatabase
from dotenv import load_dotenv
from openai import AzureOpenAI
from flask_cors import CORS

load_dotenv()

# -----------------------------------------
# Config
# -----------------------------------------
#NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
#NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
#NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
#OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
#LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
#ALLOW_WRITE = os.getenv("ALLOW_WRITE", "false").lower() in ("true", "1", "yes")

NEO4J_URI= "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Agastya@2025"
OPENAI_API_KEY = ""

AZURE_OPENAI_KEY = os.getenv("AZURE_AI_APIKEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_AI_ENDPOINT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-02-01")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT", "gpt4o-mini")



client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=AZURE_OPENAI_API_VERSION,
)

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

app = Flask(__name__)
CORS(app)

def load_schema():
    with driver.session() as s:
        labels = [r['label'] for r in s.run("CALL db.labels() YIELD label")]
        rels = [r['relationshipType'] for r in s.run("CALL db.relationshipTypes() YIELD relationshipType")]
        props = {}
        for lbl in labels:
            records = s.run(f"CALL db.properties('{lbl}')")
            props[lbl] = [r["propertyName"] for r in records]
    return labels, rels, props

LABELS, RELS, PROPS = load_schema()


def generate_cypher_query(user_input: str) -> str:
    prompt = f"""
You are an expert Cypher generator for Neo4j.
Convert the following natural language request into a Cypher query.
Return ONLY the Cypher query in JSON with key 'query'.
Example: {{"query": "MATCH (n) RETURN n LIMIT 5"}}

Database Schema:
Node Labels: {{LABELS}}
Relationship Types: {{RELS}}
Properties: {{PROPS}}

User request:
{user_input}
"""
    
    response = client.chat.completions.create(
        model=AZURE_DEPLOYMENT_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    text = response.choices[0].message.content.strip()

# --- Strip markdown code fences if present ---
    if text.startswith("```"):
        text = text.strip("`")            # remove all backticks
        text = text.replace("json", "")   # remove json language tag
        text = text.strip()

# --- Parse JSON safely ---
    try:
        data = json.loads(text)
        return data["query"]

    except Exception:
    # fallback for single-quoted json
        try:
            cleaned = text.replace("'", '"')
            data = json.loads(cleaned)
            return data["query"]
        except:
            raise ValueError(f"Invalid LLM response format: {text}")

# -------------------------------------------------------
# EXECUTE CYPHER ON NEO4J
# -------------------------------------------------------
def execute_cypher(query: str):
    with driver.session(database="pidgraph") as session:
        result = session.run(query)
        return [record.data() for record in result]

# -------------------------------------------------------
# API ENDPOINT: CHAT WITH NEO4J
# -------------------------------------------------------
@app.route("/chat", methods=["POST"])
def chat_with_graph():
    data = request.json
    user_message = data.get("message")
    
    if not user_message:
        return jsonify({"error": "Message field is required"}), 400

    try:
        cypher_query = generate_cypher_query(user_message)
        results = execute_cypher(cypher_query)

        return jsonify({
            "cypher": cypher_query,
            "results": results
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------------------------------------------
# HEALTH CHECK
# -------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}

# -------------------------------------------------------
# RUN APP
# -------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)