from collections import OrderedDict, defaultdict
from copy import deepcopy
from os import environ
from llm_interface import LLMAdvisor, ChatHistory, ChatMessage, WholeTextAdvice, ParagraphAdvice, ReplyResponse, ParagraphID, ParagraphText
from typing import Dict, List, Union, Optional, Tuple
from openai import OpenAI
import json
import difflib
import re
from context_variables import PARAGRAPH_CONTEXTS


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

    def __init__(self, model: str = "gpt-4o-mini-2024-07-18", temperature: float = 0, api_key: str = None):
        self.model = model
        api_key = api_key or environ.get("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key)
        self.temperature = temperature

        # keep feedback history for each paragraph id, for each extract
        self.chat_history: Dict[ParagraphID, Dict[str, ChatHistory]] = defaultdict(dict)
        self.paragraphs: Dict[ParagraphID, ParagraphText] = {}
        # FIXME: does interacting with the feedback (see chat_history) change the advice?
        self.advices: Dict[ParagraphID, Dict[str, str]] = defaultdict(dict)  # stores dictionary of paragraph id and a dict with {advice => text segment}
        # FIXME: needs to add initial context to various functions and adjust the prompt
        self.initial_context = None

    def _openai_call(self, messages: List[ChatMessage]) -> str:
        """
        Helper method to call the OpenAI API with a list of messages.
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        return response.choices[0].message.content.strip()

    def add_initial_context(self, context: str) -> None:
        """
        With the first question we ask the user what the general goal of the project is.
        """
        self.initial_context = context

    def process_whole_text(self, text: Dict[ParagraphID, ParagraphText]) -> WholeTextAdvice:
        raise NotImplementedError("This method is not implemented in this class.")
        """
        Process the entire text and return advice for each paragraph.
        """
        # sort text by the key
        text = OrderedDict(sorted(text.items(), key=lambda x: x[0]))
        if not self.initial_context:
            # extract initial context by summarizing the text
            messages = [
                {
                    "role": "system",
                    "content": "Please summarize the text in a few sentences.",
                },
                {
                    "role": "user",
                    "content": "\n".join(text.values()),
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

    def score_paragraph(self, paragraph_id: ParagraphID, paragraph: ParagraphText) -> float:
        # get a score on the "goodness/completeness" of the paragraph on a scale of 0 to 1
        system_prompt = self.context_prompt
        system_prompt += (
            "Analyze the following paragraph and provide a score on a scale of 0 to 1, where 0 is the worst and 1 is the best. "
            "Your score should reflect how well the paragraph answers the question and how well it is written."
            "Be critical and provide a score that reflects the quality of the paragraph. Don't hold back."
        )
        system_prompt += "The question the user is trying to answer is: " + PARAGRAPH_CONTEXTS[paragraph_id]['question']
        system_prompt += "This is the context of the paragraph: " + PARAGRAPH_CONTEXTS[paragraph_id]['context'] 
        system_prompt += "Return only the score as a float."
        system_prompt += "\n\nThis is the general outline of the project: " + self.initial_context

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": paragraph},
        ]
        response_text = self._openai_call(messages)
        retries = 3
        while retries > 0:
            try:
                score = float(response_text)
                break
            except ValueError:
                retries -= 1
                response_text = self._openai_call(messages)
        return score

    def add_paragraph(self, paragraph_id: ParagraphID, paragraph: ParagraphText) -> ParagraphAdvice:
        """
        Process and add a single paragraph.
        """
        assert self.initial_context, "You must provide an initial context before adding a paragraph."
        system_prompt = self.context_prompt
        system_prompt += "\nThe user is trying to answer the following question: " + PARAGRAPH_CONTEXTS[paragraph_id]["question"]
        system_prompt += "\nThis is the context of the paragraph: " + PARAGRAPH_CONTEXTS[paragraph_id]["context"]
        system_prompt += (
            "Analyze the following paragraph and provide constructive feedback."
            "Your goal is not to provide a full response but to instill reflection in the user."
            "Begin by analyzing the paragraph and understanding the underling message that the user want to convey."
            "Then reason about what a reader would not understand or what could be improved. Finally pry the user with some questions."
            "For each question, quote the part of the paragraph that led you to ask it and begin by summarizing the text"
            "e.g. 'Here you talk about how you would do this, but it is not clear what the final objective would be. Could you clarify that?'"
            "Return a JSON array of advice objects, where each object has keys 'extract' (a relevant excerpt) and "
            "'advice' (a suggestion for improvement). Output only valid JSON."
        )
        system_prompt += "\n\nThis is the general outline of the project: " + self.initial_context
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": paragraph},
        ]

        response_text = self._openai_call(messages)
        response_text = clean_outputs(response_text)
        retries = 3
        while retries > 0:
            try:
                advice = json.loads(response_text)
                break
            except json.JSONDecodeError:
                retries -= 1
                response_text = self._openai_call(messages)
                response_text = clean_outputs(response_text)
        else:
            raise ValueError("Failed to decode JSON response from OpenAI for add_paragraph.")
        # we expect advice to be a list of dict with keys extract and advice
        # if it's a dict with len 1, pop the value
        if isinstance(advice, dict):
            advice = advice.popitem()[1]

        # Store the paragraph.
        self.paragraphs[paragraph_id] = paragraph
        for adv in advice:
            self.advices[paragraph_id][adv["advice"]] = adv["extract"]
        return advice

    def update_paragraph(self, paragraph_id: ParagraphID, paragraph: ParagraphText) -> ParagraphAdvice:
        """
        Update an existing paragraph and return advice that focuses on the differences.
        """
        if paragraph_id not in self.paragraphs:
            # New paragraph added
            return self.add_paragraph(paragraph_id, paragraph)

        old_paragraph = self.paragraphs[paragraph_id]
        merged_paragraph = markdown_diff(old_paragraph, paragraph)
        old_advice = self.advices[paragraph_id]  # dict of advice => extract
        advice_text = "Here's the list of advices given to the previous version of the paragraph:"
        for advice, extract in old_advice.items():
            advice_text += f"\nExtract: {extract}, Advice given: {advice}"
        advice_text += "\n"
        system_prompt = self.context_prompt
        system_prompt += "\nThe user is trying to answer the following question: " + PARAGRAPH_CONTEXTS[paragraph_id]["question"] 
        system_prompt += "\nThis is the context of the paragraph: " + PARAGRAPH_CONTEXTS[paragraph_id]["context"]
        system_prompt += "\nA paragraph has been updated."
        system_prompt += advice_text
        system_prompt += (
            "Below are the merged paragraph, highlighting the changes. Focus on the differences and provide constructive feedback "
            "on the changes. Return a JSON array of advice objects, based on the previous advice given, removing advice that "
            "has been fixed and keeping advice that has not been addressed in the same wording, where each object has keys 'extract' and 'advice'. "
            "Output only valid JSON."
        )
        system_prompt += "\n\nThis is the general outline of the project: " + self.initial_context
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": merged_paragraph},
        ]

        response_text = self._openai_call(messages)
        response_text = clean_outputs(response_text)
        retries = 3
        while retries > 0:
            try:
                advice = json.loads(response_text)
                break
            except json.JSONDecodeError:
                retries -= 1
                response_text = self._openai_call(messages)
                response_text = clean_outputs(response_text)
        else:
            raise ValueError("Failed to decode JSON response from OpenAI for update_paragraph.")

        # Update the stored paragraph.
        self.paragraphs[paragraph_id] = paragraph
        # FIXME: update chat_history by poping the old paragraph and adding the new one
        return advice

    def paragraph_reply(self, paragraph_id: ParagraphID, paragraph_advice: str, reply: str = None) -> ReplyResponse:
        """
        Process the user's reply to a paragraph's feedback and return a chat history with the new response.
        If the user requested a change, also return an updated version of the paragraph.
        """
        if paragraph_id not in self.paragraphs:
            raise ValueError(f"Paragraph ID {paragraph_id} does not exist.")

        # get the given feedback for the paragraph
        extract = self.advices[paragraph_id][paragraph_advice]
        paragraph = self.paragraphs[paragraph_id]
        if paragraph_id in self.chat_history and paragraph_advice in self.chat_history[paragraph_id]:
            base_history = self.chat_history[paragraph_id][paragraph_advice]
        else:
            base_history = [
                {"role": "system", "content": self.context_prompt + " Be concise with your answers e.g. a few sentences and DON'T USE BULLET POINTS."},
                {"role": "user", "content": paragraph},
                {"role": "assistant", "content": "Considering the following extract of your paragraph: " + extract + "\n" + paragraph_advice},
            ]
        if reply is None:
            to_return = deepcopy(base_history)
            to_return[2]["content"] = paragraph_advice
            for i in range(len(to_return)):
                if to_return[i]["role"] == "assistant":
                    to_return[i]["role"] = "Assistant"
                elif to_return[i]["role"] == "user":
                    to_return[i]["role"] = "You"
            return to_return[2:]
        base_history.append({"role": "user", "content": reply})

        # system_prompt = (
        #     "You are an expert writing assistant engaged in an interactive conversation. Based on the user's reply and "
        #     "the context provided about a specific extract of a paragraph, provide a helpful response. "
        #     "If the user requests an update to the paragraph, include an updated version. "
        #     "Return your response in JSON format with two keys: 'assistant_reply' (your message to the user) "
        #     "and 'updated_paragraph' (the updated paragraph text if applicable, otherwise null). "
        #     "Output only valid JSON."
        # )

        # messages = [{"role": "system", "content": system_prompt}] + self.chat_history
        response_text = self._openai_call(base_history)

        # FIXME: currently we do not support updating the paragraph
        # response_text = clean_outputs(response_text)
        # try:
        #     response_json = json.loads(response_text)
        # except json.JSONDecodeError:
        #     raise ValueError("Failed to decode JSON response from OpenAI for paragraph_reply.")

        # assistant_reply = response_json.get("assistant_reply", "")
        # updated_paragraph = response_json.get("updated_paragraph")  # could be None

        # Append the assistant's reply to the chat history.
        assistant_message = {"role": "assistant", "content": response_text}
        base_history.append(assistant_message)
        self.chat_history[paragraph_id][paragraph_advice] = base_history

        to_return = deepcopy(base_history)
        to_return[2]["content"] = paragraph_advice
        for i in range(len(to_return)):
            if to_return[i]["role"] == "assistant":
                to_return[i]["role"] = "Assistant"
            elif to_return[i]["role"] == "user":
                to_return[i]["role"] = "You"
        return to_return[2:]
        return base_history
        # # Update the paragraph if a new version was provided.
        # if updated_paragraph is not None:
        #     self.paragraphs[paragraph_id] = updated_paragraph

        # return (self.chat_history, updated_paragraph)

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


if __name__ == "__main__":
    # tests
    advisor = OpenAIBasicAdvisor()
    advisor.add_initial_context("In this project, we want to build a house for a family in need.")
    text = {
        "q1": "The house will have a living room, two bedrooms, and a kitchen.",
        "q2": "The family has two children and a dog.",
    }
    advice_1 = advisor.add_paragraph("q1", text["q1"])
    print("Advice for paragraph 1:\n", advice_1)
    advice_2 = advisor.add_paragraph("q2", text["q2"])
    print("Advice for paragraph 2:\n", advice_2)
    updated_text = {
        "q1": "The house will have a living room, two bedrooms, a kitchen, and a backyard.",
        "q2": "The family has two children and a cat.",
    }
    updated_advice_1 = advisor.update_paragraph("q1", updated_text["q1"])
    print("Updated advice for paragraph 1:\n", updated_advice_1)
    updated_advice_2 = advisor.update_paragraph("q2", updated_text["q2"])
    print("Updated advice for paragraph 2:\n", updated_advice_2)
