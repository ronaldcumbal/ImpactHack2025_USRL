
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Union, TypedDict

# Define type aliases for readability
ParagraphID = str
ParagraphText = str
ChatMessage = TypedDict("ChatMessage", {"role": str, "content": str})  # Represents a single chat message
ChatHistory = List[ChatMessage]  # A conversation history between user and assistant
ParagraphExtractAdvice = TypedDict("ParagraphExtractAdvice", {"extract": str, "advice": str})  # Advice for an extract of a paragraph
ParagraphAdvice = List[ParagraphExtractAdvice]  # A list of advice for a paragraph
WholeTextAdvice = Dict[ParagraphID, ParagraphAdvice]  # Advice for the whole text
ReplyResponse = Tuple[ChatHistory, Union[str, None]]


class LLMAdvisor(ABC):
    """
    An abstract class that provides advice on how to improve the text based on an LLM.
    This class stores the current text so each user should have a different instance of this class.
    This class also stores all previous interactions in a chat format.
    """

    @abstractmethod
    def process_whole_text(
        self,
        text: Dict[ParagraphID, ParagraphText],
    ) -> WholeTextAdvice:
        """
        Process the entire text and return a dictionary with processed results in a chat format.
        This should be called only once at the beginning. Can be replaced with multiple calls to add_paragraph.

        Args:
            text (Dict[ParagraphID, ParagraphText]): A dictionary where the key is an immutable str representing the paragraph id
                (can be e.g. section number) and the value is the paragraph text. The paragraph ids should be sortable.

        Returns:
            WholeTextAdvice: A dictionary where the key is the paragraph id and the value is a list of advices relative to an extract of the paragraph.
        """
        pass

    @abstractmethod
    def add_paragraph(self, paragraph_id: ParagraphID, paragraph: ParagraphText) -> ParagraphAdvice:
        """
        Process and add a single paragraph and return advice in a chat format. 

        Args:
            paragraph_id (ParagraphID): The paragraph id.
            paragraph (ParagraphText): The paragraph text to be processed.

        Returns:
            ParagraphAdvice: A list of advices for an extract of the paragraph.
        """
        pass

    @abstractmethod
    def update_paragraph(self, paragraph_id: ParagraphID, paragraph: ParagraphText) -> ParagraphAdvice:
        """
        Update a paragraph and return a chat history with the assistant's (new) feedback.
        This assumes that the paragraph has already been added.
        This method will concentrate on the differences between the old and new paragraphs.
        And update the conversation accordingly.

        Args:
            paragraph_id (ParagraphID): The paragraph id.
            paragraph (ParagraphText): The paragraph text to be processed.

        Returns:
            ParagraphAdvice: A list of advices for an extract of the paragraph.
        """
        pass

    @abstractmethod
    def paragraph_reply(self, paragraph_id: ParagraphID, paragraph_extract: ParagraphText, reply: str) -> ReplyResponse:
        """
        The user replied to the assistant's feedback for a paragraph.
        Generate a response to the user's reply. If requested, update the paragraph text.

        Args:
            paragraph_id (ParagraphID): The paragraph id.
            paragraph_extract (ParagraphText): The text in the paragraph relevant to the discussion.
            reply (str): The user's reply to the assistant's feedback.

        Returns:
            ReplyResponse: A tuple with:
                - The chat history with the new response to the user.
                - An optional updated version of the paragraph text if the user requested a change (None otherwise).
        """
        pass

    @abstractmethod
    def enhance_paragraph(self, paragraph_id: Optional[ParagraphID] = None, paragraph_ids: Optional[List[ParagraphID]] = None) -> Union[str, List[str]]:
        """
        Enhance a paragraph based on the context of the surrounding paragraphs.
        This method provide a better paragraph. This should be called with either a single paragraph (e.g. if a big one) or multiple ones.

        Args:
            paragraph_id (Optional[ParagraphID]): The paragraph id.
            paragraph_ids (Optional[List[ParagraphID]]): A list of paragraph ids that are adjacent to the paragraph to enhance.

        Returns:
            Union[str, List[str]]: The enhanced paragraph text (if paragraph_id was provided) or a list of enhanced paragraph texts (if paragraph_ids were provided).
        """
        pass


if __name__ == "__main__":
    # example usage
    user2advisor = {}

    user2advisor["user1"] = LLMAdvisor()
    user2advisor["user2"] = LLMAdvisor()

    suggestions_user1 = user2advisor["user1"].process_whole_text({
        # here we can use a more or less deep hierarchy but it must be sortable and
        # handled externally.
        "1.0": "This is the first paragraph in the first section.",
        "1.1": "This is the second paragraph in the first section.",
        "2.0.1": "This is the first paragraph in the second section, first subsection.",
        "2.0.2": "This is the second paragraph in the second section, first subsection.",
    })
    print("\nSuggestions for user 1: ", suggestions_user1)

    suggestions_user2 = user2advisor["user2"].process_whole_text({
        # here we use increasing int ids, but it does not allow for insertion in the middle
        "1": "This is the first paragraph. It introduces the main ideas.",
        "2": "The second paragraph explains the details and provides examples.",
        "3": "Finally, the third paragraph concludes the discussion."
    })
    print("\nSuggestions for user 2: ", suggestions_user2)

    # Add a new paragraph to the advisor instance
    new_paragraph_id = "4"
    new_paragraph_text = "This additional paragraph offers further insights but may need clarity."
    advice_for_new_paragraph = user2advisor["user2"].add_paragraph(new_paragraph_id, new_paragraph_text)
    print("\nAdvice for the new paragraph: ", advice_for_new_paragraph)

    # Update an existing paragraph with new text
    updated_paragraph_text = "This is the updated version of the first paragraph, now with more detail and clarity."
    advice_for_updated_paragraph = user2advisor["user2"].update_paragraph("1", updated_paragraph_text)
    print("\nAdvice for the updated paragraph:, ", advice_for_updated_paragraph)

    # User replies to the advice given for a paragraph
    paragraph_id = "1"
    paragraph_extract = "This is the first paragraph."
    user_reply = "You are right, add more detail and examples."
    answer, update = user2advisor["user2"].paragraph_reply(paragraph_id, paragraph_extract, user_reply)

    # in this case update is not None because the user requested it
    print("\nUser's reply: ", user_reply)
    print("Advisor's answer: ", answer)
    print("Updated paragraph: ", update)

    # User replies to the advice given for a paragraph
    paragraph_id = "1"
    paragraph_extract = "This is the first paragraph."
    user_reply = "I disagree, this is enough detail."
    answer, update = user2advisor["user2"].paragraph_reply(paragraph_id, paragraph_extract, user_reply)

    # in this case update is None because the user did not request it
    print("\nUser's reply: ", user_reply)
    print("Advisor's answer: ", answer)
    print("Updated paragraph: ", update)
