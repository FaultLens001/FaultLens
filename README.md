# FaultLens
## Abstract
Fault Localization (FL) is a critical yet complex phase in software debugging. Over the years, numerous automated FL techniques have been developed to streamline this time-intensive process, with Large Language Models (LLMs) recently bringing FL into a new era. However, current LLM-based methods often reach premature conclusions due to extrinsic and intrinsic hallucinations. To address these challenges, we propose FaultLens, a novel FL technique that leverages LLM-based agents and a fine-grained feedback mechanism to accurately pinpoint fault locations for repository-level bugs.  Specifically, the decision-making stage of our approach starts with identifying FL candidates through an LLM-based agent. Here, location extraction validation detects extrinsic hallucinations, triggering further investigation. A defined rule determines investigation completion, while a self-check mechanism mitigates intrinsic hallucinations arising from incomplete analysis. The advanced location identification stage further minimizes intrinsic hallucinations caused by faulty reasoning. Our evaluation of the Defects4J benchmark demonstrates that FaultLens outperforms multiple FL techniques, achieving a 21.21 % improvement in Top-1 accuracy over the state-of-the-art LLM-based agent approach.

## Environment Setup
### Python dependencies
Python Version: Python 3.11

To install the required packages from your requirements.txt file, you can use the following command:
```
pip install -r requirements.txt
```

### Defects4J Dataset Setup

This project requires the Defects4J dataset, primarily using the Defects4J 2.0 environment, which includes all bugs from version 1.2 except for the four marked as deprecated. Follow the instructions at [Defects4J v2.0.0 GitHub page](https://github.com/rjust/defects4j/tree/v2.0.0) to set up Defects4J.

After completing the setup, switch Defects4J to version 1.4.0 by running the following command in the Defects4J directory:

```
git checkout v1.4.0
./init.sh
```

Then, return to the root directory of this repository and run the following commands to clone the four bugs deprecated in version 2.0 to the local environment:
```
mkdir -p data/codebase
defects4j checkout -p Closure -v 63b -w data/codebase/Closure-63
defects4j checkout -p Closure -v 93b -w data/codebase/Closure-93
defects4j checkout -p Lang -v 2b -w data/codebase/Lang-2
defects4j checkout -p Time -v 21b -w data/codebase/Time-21
```
Once the deprecated bugs are cloned, switch Defects4J back to version 2.0 by running:

```
git checkout v2.0.0
```


### Tree-Sitter Environment Setup

In addition to the `tree-sitter` dependency listed in `requirements.txt`, you will need to set up the `libtree_sitter_java.so` library for parsing Java code.

#### Steps to Install `libtree_sitter_java.so`

1. Clone the Tree-Sitter Java repository (if not already available):
   
```
git clone https://github.com/tree-sitter/tree-sitter-java.git
```
2. Build the shared library:

Navigate into the tree-sitter-java directory and run the following commands:
```
cd tree-sitter-java
gcc -fPIC -c src/parser.c -o parser.o
gcc -shared -o libtree_sitter_java.so parser.o
```
3. Set the library path in the project:

Open config/constants.py and set the path to libtree_sitter_java.so as follows:
```
TREE_SITTER_JAVA_LIB = "/path/to/your/libtree_sitter_java.so"
```
### Java 8 Setup

This project requires Java 8. Ensure that you have Java 8 installed, and specify the path in `config/constants.py`.

#### Steps to Set Up JAVA_HOME

1. Find the path to your Java 8 installation, such as `/path/to/jdk1.8.0_201`.

2. Open the `config/constants.py` file in this repository, and set the `JAVA_HOME` variable as follows:

   ```
   JAVA_HOME = "/path/to/your/java8"
    ```
### OpenAI API Key Setup

To enable OpenAI API access, please add your API key to the `OPENAI_API_KEY` variable in `config/constants.py`. 
Replace the placeholder with your actual OpenAI API key, as shown below:

```
OPENAI_API_KEY = "your_openai_api_key_here"
```

## Usage

### Run FaultLens

To run FaultLens, use the following command:

```
python3 main.py -n {agent_count} -m {model_type} -t {temperature} -l {upper_limit_of_tool_invocation_loop} -o {result_save_path}
```
agent_count: Specify the number of agents.


model_type: Specify the model type, such as gpt-4o-mini or gpt-4o-2024-08-06.


temperature: Set the temperature for the model.


result_save_path: Provide the path where results should be saved.

### Evaluate Accuracy

Run the following command to evaluate the accuracy of FaultLens results based on Top-N metrics (N=1, 3, 5):

```
python3 evaluation/evaluate.py -d {result_save_path} -o {evaluation_result_path} -v {location_extraction_validation}
```
result_save_path: The path where fault localization results were saved, with or without location extraction validation enabled.


evaluation_result_path: The path where the evaluation results will be saved.


location_extraction_validation: Indicates whether location extraction validation was enabled during the creation of result_save_path (use 1 for enabled, 0 for disabled; default is 1).


