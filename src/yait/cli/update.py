from .issues import edit
from . import main

main.add_command(edit, name="update")
