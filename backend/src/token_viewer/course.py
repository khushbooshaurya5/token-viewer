"""The course request: the model, revision, messages and switches it uses.

Plain data, so that every view can offer the course request as its default
without importing the model or a tokenizer library.
"""

COURSE_REPOSITORY: str = "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4"
"""The Hugging Face repository of the variant NVIDIA Build runs (NVFP4).

token_lab's README explains why this one: NVIDIA Build links it, and its
tokenizer files are identical to the BF16 repository's.
"""

COURSE_REVISION: str = "bee7596271d1495f6992ae224aefde4410e816b8"
"""The pinned commit: the same files every time, also when main moves on."""

COURSE_MESSAGES: list[tuple[str, str]] = [
    ("user", "Explain tokenization in one sentence."),
]
"""The course request's messages, as role and content.

The same as samples/course_messages.json in the course repository.
"""

COURSE_TEMPLATE_SWITCHES: dict[str, bool] = {"enable_thinking": False}
"""The chat template switches the course request sends.

NVIDIA's request carries them as chat_template_kwargs; the server passes them
to the chat template. Nemotron's template thinks by default, so without this
switch the text, and the tokens, would differ.
"""

COURSE_CHAT_IDS: list[int] = [
    *(10, 25708, 1010, 11, 1010),  # <|im_start|>system \n <|im_end|> \n
    *(10, 3263, 1010),  # <|im_start|>user \n
    *(2763, 44122, 10835, 3229, 1294, 1925, 19286, 1046),  # the content
    *(11, 1010),  # <|im_end|> \n
    *(10, 1503, 19464, 1010),  # <|im_start|>assistant \n
    *(12, 13),  # <think></think>
]
"""The known 24 tokens of the course request, as token_lab's tests list them."""
