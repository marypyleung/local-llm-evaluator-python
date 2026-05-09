# This file imports the engine and runs the CSV processing

import pandas as pd
from evaluator import DimensionOutcomeEvaluator

def load_data(file_path):
    """
    Loads CSV and returns a dictionary of lists for multi-dimensional analysis.
    Ensures that missing columns don't crash the script and fills NaNs.
    """
    df = pd.read_csv(file_path)
    df = df.fillna("")  # Critical: Prevents 'NoneType' errors in model encoding

    # Map your CSV column names to the internal keys here
    return {
        "questions": df['Questions'].tolist() if 'Questions' in df.columns else [],
        "expected": df['Expected Answers'].tolist() if 'Expected Answers' in df.columns else [],
        "actual": df['Actual Answers'].tolist() if 'Actual Answers' in df.columns else [],
        "claims": df['Claims'].tolist() if 'Claims' in df.columns else []
    }
    
    # Validation: Ensure core columns exist
    if not data_bundle["actual"]:
        raise ValueError("The CSV must at least contain an 'Actual Answers' column.")


def run_evaluation(input="sample_test.csv", output_path="evaluation_result.csv"):
    """
    Orchestrator script that generates results using Object and Utils together.
    """

    # 1. Initialize the "Object" (Engine)
    evaluator = DimensionOutcomeEvaluator(device=-1) # -1 for CPU, 0 for GPU
    results = []

    # 2. Load data 
    data_bundle=load_data(input)

    # Use the length of 'actual' as the master range
    num_rows = len(data_bundle["actual"])

    for i in range(num_rows):
        # Progress tracker
        print(f"🔄 Processing Question {i+1}/{num_rows}...")
        # 1. Safely extract inputs from bundle
        q = data_bundle["questions"][i] if i < len(data_bundle["questions"]) else ""
        exp = data_bundle["expected"][i] if i < len(data_bundle["expected"]) else ""
        act = data_bundle["actual"][i]
        claims = data_bundle["claims"][i] if i < len(data_bundle["claims"]) else None

        # 2. Run Engine Methods
        res_relevance = evaluator.topic_relevance(q, act)
        res_similarity = evaluator.semantic_similarity(exp, act)
        res_entailment = evaluator.entailment_outcome(act, claims)
        res_grounding = evaluator.grounding_indicator(exp, act)
        res_coverage = evaluator.coverage_indicator(exp, act)

        # 3. Construct the comprehensive row dictionary
        row_output = {
            # Original Inputs
            "question": q,
            "expected_response": exp,
            "actual_response": act,

            # Dimension 1 
            "relevance_result": res_relevance["relevance_result"],
            "relevance_score": res_relevance["relevance_score"],

            # Dimension 2
            "semantic_similarity_result": res_similarity["similarity_result"],
            "semantic_similarity_score": res_similarity["similarity_score"],
            
            # Dimension 3: Entailment (Critical Claims)
            "entailment_result": res_entailment.get("entailment_result", "ERROR"),
            "entailment_met": res_entailment.get("count_claims_met", "0 of 0"),
            
            # Dimension 4: Scope Coverage 
            "coverage_result": res_coverage["coverage_result"],
   
            # Dimension 5: Hallucination
            "hallucination_result": res_grounding["hallucination_result"]
        }
        results.append(row_output)
        
    # 4. Final Export
    df_results = pd.DataFrame(results)
    df_results.to_csv(output_path, index=False)
    print(f"✅ index: {output_path}")
    return df_results

if __name__ == "__main__":
    # You can specify your custom file names here
    run_evaluation()
