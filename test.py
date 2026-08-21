import tomllib
import json
from google import genai

with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)

client = genai.Client(api_key=secrets["GEMINI_API_KEY"])

def parse_restaurant_query(user_question):
    prompt = f"""You translate a person's plain-English restaurant search into a JSON filter. You do not answer questions about restaurant safety yourself -- you only extract search criteria.

Return ONLY valid JSON, no other text, matching this exact shape:
{{
  "min_stars": <integer 1-5, or null if not mentioned>,
  "name_keyword": <a single word or short phrase from the restaurant name/cuisine type mentioned, or null>
}}

Examples:
"cheap italian food" -> {{"min_stars": null, "name_keyword": "italian"}}
"only show me 4 star and above places" -> {{"min_stars": 4, "name_keyword": null}}
"safe sushi restaurants" -> {{"min_stars": 4, "name_keyword": "sushi"}}
"anything decent" -> {{"min_stars": 3, "name_keyword": null}}

Person's question: "{user_question}"

JSON:"""

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )
    except Exception as e:
        print("API call failed:", e)
        return None

    raw_text = response.text.strip()
    raw_text = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        print("Couldn't parse JSON, raw response was:", raw_text)
        return None
    
result = parse_restaurant_query("cheap italian food with a good safety record")
print(result)
