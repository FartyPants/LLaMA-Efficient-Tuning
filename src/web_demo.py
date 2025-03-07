# coding=utf-8
# Implements user interface in browser for fine-tuned models.
# Usage: python web_demo.py --model_name_or_path path_to_model --checkpoint_dir path_to_checkpoint


import mdtex2html
import gradio as gr

from threading import Thread
from utils import (
    Template,
    load_pretrained,
    prepare_infer_args,
    get_logits_processor
)

from transformers import TextIteratorStreamer
from transformers.utils.versions import require_version


require_version("gradio>=3.30.0", "To fix: pip install gradio>=3.30.0")


model_args, data_args, finetuning_args = prepare_infer_args()
model, tokenizer = load_pretrained(model_args, finetuning_args)

prompt_template = Template(data_args.prompt_template)
streamer = TextIteratorStreamer(tokenizer, timeout=60.0, skip_prompt=True, skip_special_tokens=True)


def postprocess(self, y):
    r"""
    Overrides Chatbot.postprocess
    """
    if y is None:
        return []
    for i, (message, response) in enumerate(y):
        y[i] = (
            None if message is None else mdtex2html.convert((message)),
            None if response is None else mdtex2html.convert(response),
        )
    return y


gr.Chatbot.postprocess = postprocess


def parse_text(text): # copy from https://github.com/GaiZhenbiao/ChuanhuChatGPT
    lines = text.split("\n")
    lines = [line for line in lines if line != ""]
    count = 0
    for i, line in enumerate(lines):
        if "```" in line:
            count += 1
            items = line.split("`")
            if count % 2 == 1:
                lines[i] = "<pre><code class=\"language-{}\">".format(items[-1])
            else:
                lines[i] = "<br /></code></pre>"
        else:
            if i > 0:
                if count % 2 == 1:
                    line = line.replace("`", "\`")
                    line = line.replace("<", "&lt;")
                    line = line.replace(">", "&gt;")
                    line = line.replace(" ", "&nbsp;")
                    line = line.replace("*", "&ast;")
                    line = line.replace("_", "&lowbar;")
                    line = line.replace("-", "&#45;")
                    line = line.replace(".", "&#46;")
                    line = line.replace("!", "&#33;")
                    line = line.replace("(", "&#40;")
                    line = line.replace(")", "&#41;")
                    line = line.replace("$", "&#36;")
                lines[i] = "<br />" + line
    text = "".join(lines)
    return text


def predict(query, chatbot, max_length, top_p, temperature, history):
    chatbot.append((parse_text(query), ""))

    input_ids = tokenizer([prompt_template.get_prompt(query, history)], return_tensors="pt")["input_ids"]
    input_ids = input_ids.to(model.device)
    gen_kwargs = {
        "input_ids": input_ids,
        "do_sample": True,
        "top_p": top_p,
        "temperature": temperature,
        "num_beams": 1,
        "max_length": max_length,
        "repetition_penalty": 1.0,
        "logits_processor": get_logits_processor(),
        "streamer": streamer
    }
    thread = Thread(target=model.generate, kwargs=gen_kwargs)
    thread.start()
    response = ""
    for new_text in streamer:
        response += new_text
        new_history = history + [(query, response)]
        chatbot[-1] = (parse_text(query), parse_text(response))
        yield chatbot, new_history


def reset_user_input():
    return gr.update(value="")


def reset_state():
    return [], []


with gr.Blocks() as demo:

    gr.HTML("""
    <h1 align="center">
        <a href="https://github.com/hiyouga/LLaMA-Efficient-Tuning" target="_blank">
            LLaMA Efficient Tuning
        </a>
    </h1>
    """)

    chatbot = gr.Chatbot()

    with gr.Row():
        with gr.Column(scale=4):
            with gr.Column(scale=12):
                user_input = gr.Textbox(show_label=False, placeholder="Input...", lines=10).style(container=False)
            with gr.Column(min_width=32, scale=1):
                submitBtn = gr.Button("Submit", variant="primary")

        with gr.Column(scale=1):
            emptyBtn = gr.Button("Clear History")
            max_length = gr.Slider(0, 2048, value=1024, step=1.0, label="Maximum length", interactive=True)
            top_p = gr.Slider(0, 1, value=0.7, step=0.01, label="Top P", interactive=True)
            temperature = gr.Slider(0, 1.5, value=0.95, step=0.01, label="Temperature", interactive=True)

    history = gr.State([])

    submitBtn.click(predict, [user_input, chatbot, max_length, top_p, temperature, history], [chatbot, history], show_progress=True)
    submitBtn.click(reset_user_input, [], [user_input])

    emptyBtn.click(reset_state, outputs=[chatbot, history], show_progress=True)

demo.queue().launch(server_name="0.0.0.0", share=True, inbrowser=True)
