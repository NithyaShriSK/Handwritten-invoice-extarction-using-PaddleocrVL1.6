import os
from paddleocr import PaddleOCRVL

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# 1. Update this to the exact folder path where your downloaded model files live
LOCAL_MODEL_DIR = "PaddlePaddle/PaddleOCR-VL-1.6"  # Replace with your actual path

# 2. Path to the image you want to extract text from
IMAGE_PATH = "your_document.png"

# Verify path before starting
if not os.path.exists(LOCAL_MODEL_DIR):
    raise FileNotFoundError(f"Model directory not found at: {LOCAL_MODEL_DIR}. Please check the path.")
if not os.path.exists(IMAGE_PATH):
    raise FileNotFoundError(f"Image not found at: {IMAGE_PATH}")

# ==============================================================================
# INITIALIZE & RUN MODEL
# ==============================================================================
print("Loading local PaddleOCR-VL-1.6 model into the pipeline...")

# Initializing the Vision-Language Model parser using your local files
pipeline = PaddleOCRVL(
    model_dir=LOCAL_MODEL_DIR, 
    pipeline_version="v1.6"
)

print(f"Extracting text from {IMAGE_PATH}...")
# Run prediction
results = pipeline.predict(IMAGE_PATH)

# ==============================================================================
# DISPLAY & SAVE RESULTS
# ==============================================================================
print("\n--- EXTRACTED RESULTS ---")
for res in results:
    # This prints the clean, high-accuracy structured text (supporting markdown format)
    res.print()
    
    # Optional: If you want to export the data into markdown files or JSON
    # res.save_to_markdown("./output_results")
    # res.save_to_json("./output_results")

print("\nExtraction complete!")