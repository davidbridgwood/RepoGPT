import unittest
from repogpt.crawler import process_file
from langchain.docstore.document import Document


class CrawlerTestCase(unittest.TestCase):

    def test_process_file(self):
        PYTHON_CODE = """
                def hello_world():
                    print("Hello, World!")

                # Call the function
                hello_world()
                """

        docs = process_file(PYTHON_CODE, "/my/file/path/", "hello.py", ".py", 100, 0)

        expected_docs = [Document(
            page_content='The following code snippet is from a file at location /my/file/path/hello.py starting at line 2. In this file there is a method named hello_world starting on line 1. The code snippet starting at line 2 is \n         ```\ndef hello_world():\n                    print("Hello, World!")\n```',
            metadata={'start_index': 17}), Document(
            page_content='The following code snippet is from a file at location /my/file/path/hello.py starting at line 5. In this file there is a method named hello_world starting on line 1. The code snippet starting at line 5 is \n         ```\n# Call the function\n                hello_world()\n```',
            metadata={'start_index': 96})]
        assert expected_docs == docs