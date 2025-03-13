from os import environ
from llm_interface import LLMAdvisor, ChatHistory, ChatMessage, WholeTextAdvice, ParagraphAdvice, ReplyResponse, ParagraphID, ParagraphText
from typing import Dict, List, Union, Optional
from openai import OpenAI
import json
import difflib
import re


def clean_outputs(response_text: str):
    """
    Cleans the passed response_text, converting it to valid JSON.

    Args:
        response_text (str): The response text to clean.
    """
    # Remove any leading or trailing whitespace
    response_text = response_text.strip()
    # Remove leading json in response
    response_cleaned = re.sub(r'json(\n)*', '', response_text)
    response_cleaned = re.sub("```", "", response_cleaned)
    return response_cleaned


# helper function for update paragraph
def markdown_diff(original, updated):
    """
    Given an original paragraph and an updated paragraph, returns a new paragraph
    that shows the differences using markdown formatting.

    Deleted content (present in original but removed in updated) will be wrapped with ~~strikethrough~~.
    Added content (new in updated) will be wrapped with **bold**.

    Args:
        original (str): The original paragraph.
        updated (str): The updated paragraph.

    Returns:
        str: The combined paragraph with markdown-formatted differences.
    """
    # Split paragraphs into words for a word-level diff.
    old_words = original.split()
    new_words = updated.split()

    # Create a SequenceMatcher object to compare the two lists.
    matcher = difflib.SequenceMatcher(None, old_words, new_words)
    result = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            # Unchanged words; add them as they are.
            result.extend(old_words[i1:i2])
        elif tag == 'delete':
            # Words deleted from the original: wrap in strikethrough.
            result.append("~~" + " ".join(old_words[i1:i2]) + "~~")
        elif tag == 'insert':
            # Words added in the updated version: wrap in bold.
            result.append("**" + " ".join(new_words[j1:j2]) + "**")
        elif tag == 'replace':
            # Words that have been replaced:
            # Show the old words with strikethrough followed by new words in bold.
            result.append("~~" + " ".join(old_words[i1:i2]) + "~~")
            result.append("**" + " ".join(new_words[j1:j2]) + "**")

    # Join the processed words back into a single string.
    return " ".join(result)


class OpenAIBasicAdvisor(LLMAdvisor):
    """
    An basic implementation of LLMAdvisor that uses OpenAI's Chat API. This implementation is yet to be tested. 
    """

    # The general and reusable prompt to give context to the model.
    context_prompt = "You are an LLM advisor that has to give feedback to grant proposal writing for proposal aimed a the non-profit World Childhood Foundation."

    def __init__(self, model: str = "gpt-4o-mini-2024-07-18", temperature: float = 0.7, api_key: str = None):
        self.model = model
        api_key = api_key or environ.get("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key)
        self.temperature = temperature
        self.chat_history: ChatHistory = []
        self.paragraphs: Dict[ParagraphID, ParagraphText] = {}
        self.initial_context = None

    def _openai_call(self, messages: List[ChatMessage]) -> str:
        """
        Helper method to call the OpenAI API with a list of messages.
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        return response.choices[0].message.content.strip()

    def add_initial_context(self, context: str) -> None:
        """
        With the first question we ask the user what the general goal of the project is.
        """
        self.initial_context = context

    def process_whole_text(self, text: Dict[ParagraphID, ParagraphText]) -> WholeTextAdvice:
        """
        Process the entire text and return advice for each paragraph.
        """
        # sort text by the key
        if not self.initial_context:
            raise NotImplementedError("You must provide an initial context before processing the whole text.")
            # extract initial context by summarizing the text
            messages = [
                {
                    "role": "system",
                    "content": "Please summarize the text in a few sentences.",
                },
                {
                    "role": "user",
                    "content": " ".join(text.values()),
                }
            ]
            response_text = self._openai_call(messages)
        # Sort paragraphs by their id and build a single prompt.
        sorted_ids = sorted(text.keys())
        paragraphs_str = "\n".join(
            [f"Paragraph ID: {pid}\nParagraph: {text[pid]}" for pid in sorted_ids]
        )
        system_prompt = self.context_prompt + (
            "Analyze the following text divided into paragraphs "
            "and provide constructive feedback for each paragraph. For each paragraph, return a list of advice items. "
            "Each advice item should be a JSON object with keys 'extract' (an excerpt of the paragraph) and "
            "'advice' (a suggestion for improvement). Return your output as a JSON object where the keys are the paragraph IDs "
            "and the values are the corresponding list of advice objects. Output only valid JSON."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": paragraphs_str},
        ]

        response_text = self._openai_call(messages)
        response_text = clean_outputs(response_text)
        try:
            whole_advice = json.loads(response_text)
        except json.JSONDecodeError:
            raise ValueError("Failed to decode JSON response from OpenAI for process_whole_text.")

        # Store the paragraphs internally.
        self.paragraphs.update(text)
        return whole_advice

    def add_paragraph(self, paragraph_id: ParagraphID, paragraph: ParagraphText) -> ParagraphAdvice:
        """
        Process and add a single paragraph.
        """
        assert self.initial_context, "You must provide an initial context before adding a paragraph."
        system_prompt = self.context_prompt + (
            "Analyze the following paragraph and provide constructive feedback. "
            "Return a JSON array of advice objects, where each object has keys 'extract' (a relevant excerpt) and "
            "'advice' (a suggestion for improvement). Output only valid JSON."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": paragraph},
        ]

        response_text = self._openai_call(messages)
        response_text = clean_outputs(response_text)
        try:
            advice = json.loads(response_text)
        except json.JSONDecodeError:
            raise ValueError("Failed to decode JSON response from OpenAI for add_paragraph.")

        # Store the paragraph.
        self.paragraphs[paragraph_id] = paragraph
        return advice

    def update_paragraph(self, paragraph_id: ParagraphID, paragraph: ParagraphText) -> ParagraphAdvice:
        """
        Update an existing paragraph and return advice that focuses on the differences.
        """
        if paragraph_id not in self.paragraphs:
            raise ValueError(f"Paragraph ID {paragraph_id} does not exist.")

        old_paragraph = self.paragraphs[paragraph_id]
        system_prompt = self.context_prompt + (
            "A paragraph has been updated. "
            "Below are the old and new versions of the paragraph. Focus on the differences and provide constructive feedback "
            "on the changes. Return a JSON array of advice objects, where each object has keys 'extract' and 'advice'. "
            "Output only valid JSON."
        )
        user_content = f"Old Paragraph:\n{old_paragraph}\n\nNew Paragraph:\n{paragraph}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        response_text = self._openai_call(messages)
        response_text = clean_outputs(response_text)
        try:
            advice = json.loads(response_text)
        except json.JSONDecodeError:
            raise ValueError("Failed to decode JSON response from OpenAI for update_paragraph.")

        # Update the stored paragraph.
        self.paragraphs[paragraph_id] = paragraph
        return advice

    def paragraph_reply(self, paragraph_id: ParagraphID, paragraph_extract: ParagraphText, reply: str) -> ReplyResponse:
        """
        Process the user's reply to a paragraph's feedback and return a chat history with the new response.
        If the user requested a change, also return an updated version of the paragraph.
        """
        if paragraph_id not in self.paragraphs:
            raise ValueError(f"Paragraph ID {paragraph_id} does not exist.")

        # Add the user's reply to the conversation.
        user_message = {
            "role": "user",
            "content": f"Regarding the following extract: '{paragraph_extract}'\nMy reply: {reply}",
        }
        self.chat_history.append(user_message)

        system_prompt = (
            "You are an expert writing assistant engaged in an interactive conversation. Based on the user's reply and "
            "the context provided about a specific extract of a paragraph, provide a helpful response. "
            "If the user requests an update to the paragraph, include an updated version. "
            "Return your response in JSON format with two keys: 'assistant_reply' (your message to the user) "
            "and 'updated_paragraph' (the updated paragraph text if applicable, otherwise null). "
            "Output only valid JSON."
        )

        messages = [{"role": "system", "content": system_prompt}] + self.chat_history
        response_text = self._openai_call(messages)
        response_text = clean_outputs(response_text)
        try:
            response_json = json.loads(response_text)
        except json.JSONDecodeError:
            raise ValueError("Failed to decode JSON response from OpenAI for paragraph_reply.")

        assistant_reply = response_json.get("assistant_reply", "")
        updated_paragraph = response_json.get("updated_paragraph")  # could be None

        # Append the assistant's reply to the chat history.
        assistant_message = {"role": "assistant", "content": assistant_reply}
        self.chat_history.append(assistant_message)

        # Update the paragraph if a new version was provided.
        if updated_paragraph is not None:
            self.paragraphs[paragraph_id] = updated_paragraph

        return (self.chat_history, updated_paragraph)

    def enhance_paragraph(
        self, paragraph_id: Optional[ParagraphID] = None, paragraph_ids: Optional[List[ParagraphID]] = None
    ) -> Union[str, List[str]]:
        """
        Enhance one or more paragraphs based on the context.
        """
        system_prompt = (
            "You are an expert writing assistant. Enhance the following paragraph to improve its clarity, coherence, "
            "and style. Return only the enhanced paragraph text."
        )

        if paragraph_id is not None and paragraph_ids is not None:
            raise ValueError("Provide either 'paragraph_id' or 'paragraph_ids', not both.")

        if paragraph_id is not None:
            if paragraph_id not in self.paragraphs:
                raise ValueError(f"Paragraph ID {paragraph_id} does not exist.")
            paragraph_text = self.paragraphs[paragraph_id]
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": paragraph_text},
            ]
            enhanced = self._openai_call(messages)
            return enhanced

        elif paragraph_ids is not None:
            enhanced_list = []
            for pid in paragraph_ids:
                if pid not in self.paragraphs:
                    raise ValueError(f"Paragraph ID {pid} does not exist.")
                paragraph_text = self.paragraphs[pid]
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": paragraph_text},
                ]
                enhanced = self._openai_call(messages)
                enhanced_list.append(enhanced)
            return enhanced_list

        else:
            raise ValueError("Either 'paragraph_id' or 'paragraph_ids' must be provided.")
