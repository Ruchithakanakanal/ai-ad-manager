import os
import re

# folder where your backend code is
BASE_DIR = "backend"

# mapping of fixes
REPLACEMENTS = {
    r"from database": "from backend.database",
    r"from models": "from backend.models",
    r"from routes": "from backend.routes",
    r"from services": "from backend.services",
    r"import database": "import backend.database",
    r"import models": "import backend.models",
    r"import routes": "import backend.routes",
    r"import services": "import backend.services",
}

def fix_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    original = content

    for pattern, replacement in REPLACEMENTS.items():
        content = re.sub(pattern, replacement, content)

    if content != original:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✔ Fixed: {file_path}")

def walk_folder(folder):
    for root, _, files in os.walk(folder):
        for file in files:
            if file.endswith(".py"):
                fix_file(os.path.join(root, file))

if __name__ == "__main__":
    walk_folder(BASE_DIR)
    print("✅ Done fixing imports!")