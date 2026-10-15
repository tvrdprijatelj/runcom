import os
import requests
import zipfile

def download_file(url, filename, folder="Nedladdningar"):
    """Laddar ner en fil med en framstegsindikator."""
    if not os.path.exists(folder):
        os.makedirs(folder)
        
    filepath = os.path.join(folder, filename)
    print(f"📥 Laddar ner: {filename}...")
    
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = int((downloaded / total_size) * 100)
                        print(f"   Framsteg: {percent}%", end="\r")
        print(f"\n✅ Klart! Sparad i: {filepath}")
        return filepath
    else:
        print(f"❌ Misslyckades att ladda ner {filename}. Statuskod: {response.status_code}\n")
        return None

def extract_zip(zip_path, extract_to="Nedladdningar"):
    """Extraherar en ZIP-fil till den angivna mappen."""
    print(f"📂 Extraherar {os.path.basename(zip_path)}...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Skapar ett unikt mappnamn baserat på zip-filens namn utan ändelse
            folder_name = os.path.splitext(os.path.basename(zip_path))[0]
            target_dir = os.path.join(extract_to, folder_name)
            
            zip_ref.extractall(target_dir)
            print(f"✨ Allt innehåll har extraherats till mappen: {target_dir}\n")
    except Exception as e:
        print(f"⚠️ Kunde inte extrahera filen: {e}\n")

def get_latest_python_windows():
    """Hämtar URL till den senaste stabila Python-installeraren för Windows (64-bit)."""
    print("🔍 Söker efter senaste Python-versionen...")
    try:
        res = requests.get("https://endoflife.date").json()
        latest_version = res[0]['latest']  # Fångar den absolut senaste skarpa releasen (t.ex. 3.14.x)
        
        download_url = f"https://python.org{latest_version}/python-{latest_version}-amd64.exe"
        filename = f"python-{latest_version}-amd64.exe"
        
        print(f"✨ Hittade senaste Python-versionen: {latest_version}")
        return download_url, filename
    except Exception as e:
        print(f"⚠️ Kunde inte hämta senaste versionen automatiskt: {e}")
        return "https://python.org3.14.8/python-3.14.8-amd64.exe", "python-3.14.8-amd64.exe"

def download_all_from_latest_release(owner, repo, folder="Nedladdningar"):
    """Hämtar källkods-zip och alla uppladdade assets från senaste GitHub-releasen."""
    print(f"🔍 Söker efter senaste utgåvan av {owner}/{repo} på GitHub...")
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    
    response = requests.get(url)
    if response.status_code != 200:
        print(f"❌ Kunde inte hämta GitHub-release. Statuskod: {response.status_code}")
        return

    data = response.json()
    tag_name = data.get("tag_name", "latest")
    print(f"✨ Hittade utgåva: {tag_name}")

    # 1. Hantera källkoden (Allt i repon som ZIP)
    zip_url = data.get("zipball_url")
    if zip_url:
        zip_filename = f"{repo}-{tag_name}-source.zip"
        downloaded_zip = download_file(zip_url, zip_filename, folder)
        if downloaded_zip:
            # Extrahera källkoden automatiskt
            extract_zip(downloaded_zip, folder)

    # 2. Hantera eventuella tillhörande Assets (t.ex. kompilerade program, exe-filer, binärer)
    assets = data.get("assets", [])
    if assets:
        print(f"📦 Hittade {len(assets)} tillhörande fil(er) i utgåvan:")
        for asset in assets:
            asset_url = asset["browser_download_url"]
            asset_name = asset["name"]
            download_file(asset_url, asset_name, folder)
    else:
        print("ℹ️ Inga extra installationsfiler (Assets) hittades i releasen. Endast källkod laddades ner.")

# --- KÖR ASSISTENTEN ---
if __name__ == "__main__":
    # Inställningar för din specifika repo
    OWNER = "tvrdprijatelj"
    REPO = "runcom"
    DOWNLOAD_FOLDER = "Nedladdningar"

    print("=== DOWNLOAD ASSISTANT STARTAR ===\n")
    
    # 1. Hämta och ladda ner senaste Python
    py_url, py_file = get_latest_python_windows()
    download_file(py_url, py_file, DOWNLOAD_FOLDER)
    print("-" * 50)
    
    # 2. Hämta allt från din GitHub-release samt extrahera källkoden
    download_all_from_latest_release(OWNER, REPO, DOWNLOAD_FOLDER)
        
    print("=== ALLA INTEGRATIONER OCH EXTRAHERINGAR KLARA ===")
