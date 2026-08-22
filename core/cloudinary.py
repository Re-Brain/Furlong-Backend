import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)

def upload_image(file_bytes: bytes, folder: str = "horses") -> dict:
    return cloudinary.uploader.upload(
        file_bytes,
        folder=folder,
        transformation=[
            {"width": 800, "crop": "limit"},
            {"quality": "auto"},
            {"fetch_format": "auto"},
        ],
    )

def delete_image(public_id: str) -> None:
    cloudinary.uploader.destroy(public_id)

def upload_document(file_bytes: bytes, folder: str = "horse_documents") -> dict:
    # No transformation pipeline — these are legal/identity documents (PDFs or
    # photographed paperwork), not display photos. resource_type "auto" lets
    # Cloudinary route images vs. PDFs vs. other files to the right bucket.
    return cloudinary.uploader.upload(
        file_bytes,
        folder=folder,
        resource_type="auto",
    )

def delete_document(public_id: str, resource_type: str) -> None:
    # resource_type must match what the asset was actually stored as (see
    # upload_document) or Cloudinary silently fails to find it.
    cloudinary.uploader.destroy(public_id, resource_type=resource_type)
