import requests
import pandas as pd

CKAN_BASE = "https://ckan0.cf.opendata.inter.prod-toronto.ca"
PACKAGE_ID = "dinesafe"

def get_package_metadata():
    url = f"{CKAN_BASE}/api/3/action/package_show"
    response = requests.get(url, params={"id": PACKAGE_ID})
    data = response.json()
    return data["result"]

def pick_current_csv(resources):
    csv_resources = [r for r in resources if r["format"] == "CSV"]
    return max(csv_resources, key=lambda r: r["last_modified"])

def main():
    package = get_package_metadata()
    resource = pick_current_csv(package["resources"])
    print("Using:", resource["name"], "| last modified:", resource["last_modified"])

    df = pd.read_csv(resource["url"])
    print(df.shape)

    if len(df) == 0:
        print("Got 0 rows back — something's wrong upstream. Not overwriting existing file.")
        return

    df.to_csv("data/raw/Dinesafe.csv", index=False)
    print("Saved to data/raw/Dinesafe.csv")

if __name__ == "__main__":
    main()
