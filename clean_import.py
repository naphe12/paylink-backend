import subprocess


def run(command):
    print(f"Running: {command}")
    subprocess.run(command, shell=True, check=True)

# Nettoyage des imports inutiles et doublons
run("autoflake --remove-all-unused-imports --remove-duplicate-keys --in-place --recursive .")

# Tri des imports
run("isort .")

# Formatage du code
run("black .")