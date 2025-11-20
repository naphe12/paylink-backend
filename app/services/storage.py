import uuid
from app.core.supabase import supabase

async def upload_to_storage(file):
    if not file:
        return None

    ext = file.filename.split(".")[-1]
    new_name = f"{uuid.uuid4()}.{ext}"

    data = file.file.read()

    supabase.storage.from_("kyc-documents").upload(new_name, data)
    public_url = supabase.storage.from_("kyc-documents").get_public_url(new_name)

    return public_url
