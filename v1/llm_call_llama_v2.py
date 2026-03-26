import ollama
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import json
import re
import time 

class SimpleRAG:
    def __init__(self, model_name="llama3.2:3b"):
        self.llm_model = model_name
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        self.chunks = []
        self.embeddings = None
        self.metadata = []
    
    def add_documents(self, texts, metadata=None):
        """Add documents to the index"""
        self.chunks.extend(texts)
        if metadata:
            self.metadata.extend(metadata)
        
        # Generate embeddings
        print(f"Generating embeddings for {len(texts)} documents...")
        new_embeddings = self.embedder.encode(texts)
        
        if self.embeddings is None:
            self.embeddings = new_embeddings
        else:
            self.embeddings = np.vstack([self.embeddings, new_embeddings])
        
        print(f"Total chunks indexed: {len(self.chunks)}")
    
    def retrieve(self, query, top_k=10):
        """Retrieve most relevant chunks"""
        if not self.chunks:
            return []
        
        query_embedding = self.embedder.encode([query])
        similarities = cosine_similarity(query_embedding, self.embeddings)[0]
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        
        results = []
        for idx in top_indices:
            results.append({
                'content': self.chunks[idx],
                'score': float(similarities[idx]),
                'metadata': self.metadata[idx] if self.metadata else None
            })
        
        return results
    
    def llm_call(self, chunk):
        """Query with RAG"""
        # Retrieve relevant context
        #results = self.retrieve(question, top_k=top_k)
        
        if not chunk:
            return "No relevant context found."
        
        # Build context
        #context = "\n\n---\n\n".join([r['content'] for r in results])
        context = chunk
        
        #Define prompt template
        TRIVIA_ANALYST_PROMPT = """
You are an expert trivia analyst. Your goal is to evaluate each "Potential Q&A Pair" extracted from chat logs to determine if a question was successfully asked and correctly answered.

### Semantic Gating Logic (The "Is it Trivia?" Test):
Before analyzing the answer, classify the Intent of the "Q" block.
TRIVIA: The prompt seeks a specific fact, name, connection, or completion of a riddle. It usually has a "point value" or is part of a numbered sequence.
ADMIN: Logistics about the quiz (e.g., "When is the next round?", "Can we move the time?"). [Mark Invalid]
SOCIAL/RHETORICAL: Sarcasm, venting, hyperbole, or feedback (e.g., "Who did this?", "Why is this so hard?", "Brilliant quiz!"). [Mark Invalid]
CLARIFICATION: A follow-up question about a current trivia round (e.g., "Can you repeat the clue?"). [Mark Invalid]
For every "Q" block provided, you must perform a "Chain of Contradiction" analysis:
Surface Sentiment: What does the literal grammar suggest? (e.g., "Asking for a person's identity").
True Intention: What is the speaker actually doing? (e.g., "Venting frustration," "Joke/Sarcasm," "Scheduling a meeting").
The Fact Test: If the question does not have a concrete, third-party verifiable fact as an answer, it is NOT trivia.




### Analysis Logic:
If and only if the intent is TRIVIA:
1. **Identify Roles:** The "Asker" is defined as the username who posted the "Q" block. Any message in the discussion from this same username tagged as `feedback/hint/confirmation` or `Potential confirmation` is the authoritative source for correctness.
2. **Evaluate the Question:** Check the "Q" block. Is it a coherent question or a request for information? 
3. **Evaluate the Answer:** Analyze the "A" block and any `possible answer` tags and identify the potential correct answer. 
4. **Verify Correctness:** 
    - Search the `feedback/hint/confirmation` tags for affirmative signals from the Asker (e.g., "✓", "Correct", "Yes", "Exactly", or the Asker repeating the respondent's answer in a positive context). If this is not available, analyze the discussion to find the most likely correct answer. 
    - **Entity Resolution:** Treat different parts of a name (e.g., "Sanath" and "Jayasuriya") or common nicknames as the same answer.
    - If the Asker provides a feedback message that contradicts the `possible answer`, mark `is_confirmed_correct` as false.
    - The Tally Rule: If the Asker posts a message containing names and numbers (e.g., "Nikunj 10"), treat the username with the score as the solver_username.
    - The Race Condition: In chat logs, the "correct" answer is usually the first person to say the specific entity before the Asker closes the round.
    - Implicit Confirmation: Phrases like "Next" or "Part 2" from the Asker immediately following a set of answers imply the previous question was resolved.

### Required Output (JSON):
{{
  "question_validity": {{
    "is_valid": boolean,
    "intent_type": "TRIVIA | ADMIN | SOCIAL | CLARIFICATION",
    "reason": "Explain why it is or isn't trivia. For example: 'Hyperbolic venting about a mistake' vs 'A riddle about a movie plot.'"
  }},
  "answer_analysis": {{
    "final_answer_found": "The specific name, entity, or fact identified.",
    "is_confirmed_correct": boolean,
    "confidence_score": float,
    "verification_source": "The specific message or tag that validated the answer.",
    "summary" : "A five line summary of the "Potential Answers and Discussion" block."
  }},
  "metadata": {{
   "asker_username": "Name",
   "solver_username": "Name of the first correct respondent"
  }},
  "final_QA_pair: {{"Question": "Full Q block text",
   "Answer": "Full message text of the first correct answer"
  }}
  }}
  ### Data to Process:
    {chat_data}

"""
        # Create prompt
        #prompt = f"""Based on the following chat excerpts, answer the question.
        prompt = TRIVIA_ANALYST_PROMPT.format(chat_data = chunk)

        
        # Query LLM
        try:
            response = ollama.generate(
                model=self.llm_model,
                prompt=prompt
            )
            return response['response']
        except Exception as e:
            return f"Error querying LLM: {e}"
    
    def save_index(self, filepath):
        """Save index to disk"""
        data = {
            'chunks': self.chunks,
            'embeddings': self.embeddings.tolist() if self.embeddings is not None else None,
            'metadata': self.metadata
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        print(f"Index saved to {filepath}")
    
    def load_index(self, filepath):
        """Load index from disk"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.chunks = data['chunks']
        self.embeddings = np.array(data['embeddings']) if data['embeddings'] else None
        self.metadata = data['metadata']
        print(f"Index loaded: {len(self.chunks)} chunks")


# Usage Example
def load_chat_file(filepath):
    """Load and split chat file into chunks"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by Q&A pairs or by message blocks
    chunks = []
    current_chunk = []
    
    for line in content.split('\n'):
        if line.startswith('==='):
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
        current_chunk.append(line)
    
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    return chunks


# Initialize RAG
if __name__ == "__main__":
    rag = SimpleRAG(model_name="llama3.2:3b")

    # Load your chat file
    chunks = load_chat_file('chat_2026-02-11_qa_pairs.txt')
    rag.add_documents(chunks)

    # Save index (optional - for reuse)
    rag.save_index('chat_index.json')


    # Query
    test_chunk = rag.chunks[87]
    llm_begin_time  = time.perf_counter()
    answer = rag.llm_call(test_chunk)
    llm_end_time = time.perf_counter()
    print(answer)
    print("\n THIS LLAMA QUERY TOOK %f seconds" %(llm_end_time - llm_begin_time))

    """ # Get relevant chunks directly
    results = rag.retrieve("movie questions", top_k=5)
    for i, result in enumerate(results, 1):
        print(f"\n--- Result {i} (score: {result['score']:.3f}) ---")
        print(result['content'][:]) """