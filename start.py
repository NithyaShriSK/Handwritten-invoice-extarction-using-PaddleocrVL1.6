import sys
from PIL import Image
import torch
from transformers import AutoConfig, AutoProcessor, AutoModel

# ---- Settings ----
model_path = "PaddlePaddle/PaddleOCR-VL-1.6"
image_path = "invoice.png"
task = "ocr" # Options: 'ocr' | 'table' | 'chart' | 'formula' | 'spotting' | 'seal'
# ------------------

# ---- Image Preprocessing For Spotting ----
image = Image.open(image_path).convert("RGB")
orig_w, orig_h = image.size
spotting_upscale_threshold = 1500

if task == "spotting" and orig_w < spotting_upscale_threshold and orig_h < spotting_upscale_threshold:
    process_w, process_h = orig_w * 2, orig_h * 2
    try:
        resample_filter = Image.Resampling.LANCZOS
    except AttributeError:
        resample_filter = Image.LANCZOS
    image = image.resize((process_w, process_h), resample_filter)

# Set max_pixels: use 1605632 for spotting, otherwise use default ~1M pixels
max_pixels = 2048 * 28 * 28 if task == "spotting" else 1280 * 28 * 28
# ---------------------------

# -------- Inference --------
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
PROMPTS = {
    "ocr": "OCR:",
    "table": "Table Recognition:",
    "formula": "Formula Recognition:",
    "chart": "Chart Recognition:",
    "spotting": "Spotting:",
    "seal": "Seal Recognition:",
}

print("Loading config and registering custom model class...")
config = AutoConfig.from_pretrained(model_path, trust_remote_code=True)

# ------------------------------------------------------------------------
# 🔥 FIXED MONKEY-PATCH: Remap inputs_embeds (plural) to input_embeds (singular)
# ------------------------------------------------------------------------
def apply_causal_mask_patch():
    modeling_module = None
    for mod_name, mod_obj in sys.modules.items():
        if "modeling_paddleocr_vl" in mod_name:
            modeling_module = mod_obj
            break

    if modeling_module is not None and not hasattr(modeling_module, "_patched"):
        print("Found custom model module. Applying variable remapping patch...")
        original_create_causal_mask = modeling_module.create_causal_mask

        def patched_create_causal_mask(*args, **kwargs):
            # If transformers passed 'inputs_embeds', map it over to 'input_embeds'
            if "inputs_embeds" in kwargs:
                kwargs["input_embeds"] = kwargs.pop("inputs_embeds")
            return original_create_causal_mask(*args, **kwargs)

        modeling_module.create_causal_mask = patched_create_causal_mask
        modeling_module._patched = True
        return True
    return False

# Attempt early patch injection
apply_causal_mask_patch()
# ------------------------------------------------------------------------

print("Loading model parameters onto GPU...")
model = AutoModel.from_pretrained(
    model_path, 
    config=config,
    torch_dtype=torch.bfloat16,
    trust_remote_code=True
).to(DEVICE).eval()

# Check and enforce the patch again post-model load instantiation
apply_causal_mask_patch()

processor = AutoProcessor.from_pretrained(
    model_path, 
    trust_remote_code=True
)

messages = [
    {
        "role": "user",
        "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": PROMPTS[task]},
        ]
    }
]

min_pix = processor.image_processor.min_pixels if hasattr(processor.image_processor, 'min_pixels') else 14

inputs = processor.apply_chat_template(
    messages,
    add_generation_prompt=True,
    tokenize=True,
    return_dict=True,
    return_tensors="pt",
    images_kwargs={"size": {"shortest_edge": min_pix, "longest_edge": max_pixels}},
).to(model.device)

print("Running OCR text generation inference...")
with torch.no_grad():
    outputs = model.generate(**inputs, max_new_tokens=512)

result = processor.decode(outputs[0][inputs["input_ids"].shape[-1]:-1], skip_special_tokens=True)

print("\n--- OCR RESULT ---")
print(result)