from langchain.docstore.document import Document
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import Language, RecursiveCharacterTextSplitter
from langchain_community.vectorstores import DeepLake
from repogpt.parsers.python_parser import PythonParser
from repogpt.parsers.treesitter import TreeSitterParser
from repogpt.parsers.cpp_treesitter_parser import CppTreeSitterParser
from repogpt.parsers.java_treesitter_parser import JavaTreeSitterParser
from repogpt.parsers.js_treesitter_parser import JsTreeSitterParser
from repogpt.parsers.go_treesitter_parser import GoTreeSitterParser
from repogpt.parsers.treesitter import FileSummary
from tqdm import tqdm
from typing import List, Optional
import os
import fnmatch
import logging
from functools import partial

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repogpt_crawler_logger")

LANG_MAPPING = {
    '.py': Language.PYTHON,
    '.cpp': Language.CPP,
    '.cc': Language.CPP,
    '.cxx': Language.CPP,
    '.h': Language.CPP,
    '.hpp': Language.CPP,
    '.java': Language.JAVA,
    '.go': Language.GO,
    '.js': Language.JS,
    '.ts': Language.JS,
    '.php': Language.PHP,
    '.proto': Language.PROTO,
    '.rs': Language.RST,
    '.rb': Language.RUBY,
    '.scala': Language.SCALA,
    '.swift': Language.SWIFT,
    '.md': Language.MARKDOWN,
    '.tex': Language.LATEX,
    '.html': Language.HTML
}


class FileProperties:

    def __init__(self, dir_path: str, file_name: str, extension: str):
        self.dir_path = dir_path
        self.file_name = file_name
        self.extension = extension


def contains_hidden_dir(dir_path: str) -> bool:
    """Check if a directory path contains a hidden directory"""
    directories = dir_path.split('/')
    return any(fnmatch.fnmatch(directory, '.*') for directory in directories)


def is_git_dir(dir_path: str) -> bool:
    """Check if directory path points to a valid git directory"""
    git_dir = os.path.join(dir_path, '.git')
    return os.path.isdir(git_dir)


def process_file(
        file_contents: List[Document],
        dir_path: str,
        file_name: str,
        extension: str,
        chunk_size: int,
        chunk_overlap: int
) -> List[Document]:
    """For a given file, get the summary, split into chunks and create context document chunks to be indexed"""
    file_doc = file_contents[0]

    # get file summary for raw file
    # TODO: Add parsers for more languages
    if extension == '.py':
        file_summary = PythonParser.get_file_summary(file_doc.page_content, file_name)
    elif extension == '.cpp':
        file_summary = CppTreeSitterParser.get_file_summary(file_doc.page_content, file_name)
    elif extension == '.java':
        file_summary = JavaTreeSitterParser.get_file_summary(file_doc.page_content, file_name)
    elif extension == '.js':
        file_summary = JsTreeSitterParser.get_file_summary(file_doc.page_content, file_name)
    elif extension == '.go':
        file_summary = GoTreeSitterParser.get_file_summary(file_doc.page_content, file_name)
    else:
        file_summary = FileSummary()

    # split file contents based on file extension
    splitter = RecursiveCharacterTextSplitter.from_language(
        language=LANG_MAPPING[extension],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        add_start_index=True)
    split_docs = splitter.split_documents(file_contents)

    # add file path, starting line and summary to each chunk
    for doc in split_docs:
        starting_line = file_doc.page_content[:doc.metadata['start_index']].count('\n') + 1
        ending_line = starting_line + doc.page_content.count('\n')
        doc.metadata['starting_line'] = starting_line
        doc.metadata['ending_line'] = ending_line

        # get methods and classes associated with chunk
        method_class_summary = TreeSitterParser.get_closest_method_class_in_snippet(file_summary,
                                                                                    starting_line,
                                                                                    ending_line)
        doc.page_content = f"The following code snippet is from a file at location " \
                           f"{os.path.join(dir_path, file_name)} " \
                           f"starting at line {starting_line} and ending at line {ending_line}. " \
                           f"{method_class_summary} " \
                           f"The code snippet starting at line {starting_line} and ending at line " \
                           f"{ending_line} is \n ```\n{doc.page_content}\n``` "

    return split_docs


def filter_files(root_dir: str) -> List[FileProperties]:
    """Crawl the root directory and filter out invalid files that will not be indexed"""
    if not is_git_dir(root_dir):
        raise ValueError(f"{root_dir} is not a valid git root directory")

    files_to_crawl = []
    for dir_path, dir_names, filenames in os.walk(root_dir):
        for file in filenames:
            _, extension = os.path.splitext(file)
            # only want to crawl accepted file types and files not in hidden directories
            if extension in LANG_MAPPING and not contains_hidden_dir(dir_path):
                files_to_crawl.append(FileProperties(dir_path, file, extension))
            else:
                logger.info(f"Skipping {os.path.join(dir_path, file)} - File or directory type not supported.")
    return files_to_crawl


def process_and_split(file: FileProperties, chunk_size: int, chunk_overlap: int) -> Optional[List[Document]]:
    """For a given file, load it into memory and process it"""
    try:
        loader = TextLoader(os.path.join(file.dir_path, file.file_name), encoding='utf-8')
        chunks = process_file(loader.load(), file.dir_path, file.file_name, file.extension, chunk_size, chunk_overlap)
    except Exception as e:
        logger.error(f"Error processing file {os.path.join(file.dir_path, file.file_name)}. Skipping file. {e}")
        return None
    return chunks


def crawl_and_split(root_dir: str, chunk_size: int = 3000, chunk_overlap: int = 0) -> List[Document]:
    """Crawl git directory and process files"""
    filtered_files = filter_files(root_dir)

    process_and_split_partial_function = partial(process_and_split, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    split_docs = []
    with tqdm(total=len(filtered_files), desc='Chunking documents...', ncols=80) as pbar:
        for ff in filtered_files:
            docs = process_and_split_partial_function(ff)
            if docs:
                split_docs.extend(docs)
            pbar.update()

    return split_docs


def index(docs: List[Document], embedding_type, vs_path: str):
    return DeepLake.from_documents(docs, embedding_type, dataset_path=vs_path)
