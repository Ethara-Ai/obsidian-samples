---
name: image-generation
description: Generate images from a text prompt with the image model this run provides, and save them as files.
metadata: {"clawdbot":{"requires":{"bins":["python3"]}}}
---

# Image generation

Create images from a text description through the harness's image gateway.

## Check the model

```bash
python3 {baseDir}/scripts/generate_image.py --info
```

Prints the model id this run uses, whether image generation is configured, and `images_per_task`: how many images this task may request, has requested, and has left.

## Generate

```bash
python3 {baseDir}/scripts/generate_image.py "a watercolor of a lighthouse at dawn, soft light" \
  --out /root/workspace/lighthouse --format png
python3 {baseDir}/scripts/generate_image.py "three product shots of a blue ceramic mug on linen" \
  --out /root/workspace/mug --n 3 --size 1536x1024
```

- `--out` is a path prefix. One image is written as `<out>.<format>`; several as `<out>_1.<format>`, `<out>_2.<format>`, and so on.
- `--n` is 1 to 10. `--size` is `WIDTHxHEIGHT` and sets the aspect ratio. `--format` is `webp` (default), `png`, or `jpeg`.
- The script prints the files it wrote and the model's usage numbers.

## What you should know

- Every request is metered against this run. Generate what the task needs, not variations for their own sake.
- Each task may request a limited number of images in total, counting every `--n` asked for, failed requests included. Past it, generation is refused with `budget_exceeded` (HTTP 429); stop generating and finish the task with the images you have.
- Describe the image fully in the prompt; the model works from the prompt alone.
- If the tool is not configured for this run, `--info` says so and generation is refused with `not_configured`.
