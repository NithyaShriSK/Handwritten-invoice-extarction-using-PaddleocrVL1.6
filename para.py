import os
import sys
import torch
from PIL import Image

# ================= TRANSFORMERS PATCH =================

import transformers

try:
    import transformers.modeling_rope_utils as rope_utils

    # Disable strict rope validation for PaddleOCR-VL
    rope_utils.rope_config_validation = lambda *args, **kwargs: None

except Exception:
    pass


from transformers import (
    AutoProcessor,
    AutoModelForImageTextToText,
    AutoConfig
)


# ================= SETTINGS =================

model_path = "PaddlePaddle/PaddleOCR-VL-1.6"

image_path = "invoice.png"


# ============================================


DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print(f"[Device Status] Using Execution Target: {DEVICE.upper()}")


COMPUTE_DTYPE = (
    torch.bfloat16
    if DEVICE == "cuda"
    else torch.float32
)



# ================= IMAGE ====================


if not os.path.exists(image_path):
    raise FileNotFoundError(image_path)


image = Image.open(image_path).convert("RGB")


print("Original Image Size:", image.size)


# Upscale small invoices

if image.width < 1200:

    image = image.resize(
        (
            image.width * 2,
            image.height * 2
        ),
        Image.Resampling.LANCZOS
    )


print("Processed Image Size:", image.size)



# ================= PROMPT ===================


prompt = """
OCR this invoice completely.

Extract every visible text.

Include:
- Company details
- Customer details
- Invoice number
- Date
- GST information
- Product table
- Quantity
- Amount
- Tax
- Total
- Bank details
- Terms and conditions

Read from top to bottom.
Do not summarize.
Return the exact text.
"""



# ================= CONFIG ===================


print("Loading model configuration...")


config = AutoConfig.from_pretrained(
    model_path,
    trust_remote_code=True
)



# PaddleOCR-VL needs text_config

if not hasattr(config, "text_config"):

    config.text_config = config



# Keep required rope_parameters

rope_parameters = {

    "rope_type": "default",

    "rope_theta": 10000.0

}


config.rope_parameters = rope_parameters


if hasattr(config, "text_config"):

    config.text_config.rope_parameters = rope_parameters



print("Configuration ready")



# ================= MODEL ====================


print("Loading model...")


model = AutoModelForImageTextToText.from_pretrained(

    model_path,

    config=config,

    torch_dtype=COMPUTE_DTYPE,

    trust_remote_code=True,

    device_map="auto"

)


model.eval()


print("Model loaded successfully")



# ================= PROCESSOR ===============


print("Loading processor...")


processor = AutoProcessor.from_pretrained(

    model_path,

    trust_remote_code=True

)



# ================= INPUT ====================


messages = [

    {

        "role": "user",

        "content": [

            {

                "type": "image",

                "image": image

            },

            {

                "type": "text",

                "text": prompt

            }

        ]

    }

]



print("Preparing input...")


inputs = processor.apply_chat_template(

    messages,

    add_generation_prompt=True,

    tokenize=True,

    return_dict=True,

    return_tensors="pt"

)



inputs = inputs.to(model.device)



# ================= OCR ======================


print("Running OCR...")


with torch.inference_mode():

    output = model.generate(

        **inputs,

        max_new_tokens=2048,

        do_sample=False

    )



# Remove prompt tokens

output_tokens = output[

    0,

    inputs["input_ids"].shape[-1]:

]


result = processor.decode(

    output_tokens,

    skip_special_tokens=True

)



print("\n============== OCR RESULT ==============\n")

print(result)

print("\n========================================")