import json
import asyncio
import os
from pipeline import ExtractionPipeline
from schema import CompanyList
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=True)

async def main():
    print("Workflow 1: Extraction starting with iterative processing...")
    pipeline = ExtractionPipeline()
    
    theses = ["AI", "Defense", "Electrification", "Gold", "Nuclear", "Reshoring"]
    consolidated = {} # Key: ticker.exchange

    for thesis in theses:
        print(f"\n--- Processing Thesis: {thesis} ---")
        
        # Prepare existing data for refinement
        existing_data = list(consolidated.values())
        
        result = await pipeline.run_thesis(thesis, existing_data)
        
        companies_found = []
        if isinstance(result, CompanyList):
            companies_found = result.model_dump()['companies']
        else:
            try:
                companies_found = json.loads(result)['companies']
            except Exception as e:
                print(f"Failed to parse extraction result for {thesis}: {e}")
                continue

        for c in companies_found:
            key = f"{c['ticker']}.{c['exchange']}"
            
            # Extract the thesis reference for this company (should be only one per run)
            # The LLM should return it in c['theses']
            new_theses_refs = c['theses']
            
            if key not in consolidated:
                consolidated[key] = {
                    "name": c['name'],
                    "ticker": c['ticker'],
                    "exchange": c['exchange'],
                    "theses": new_theses_refs
                }
            else:
                # Merge logic
                existing_entry = consolidated[key]
                existing_thesis_names = {t['thesis_name'] for t in existing_entry['theses']}
                
                for nt in new_theses_refs:
                    if nt['thesis_name'] not in existing_thesis_names:
                        # New thesis for existing company
                        existing_entry['theses'].append(nt)
                    else:
                        # Refinement: update the type if it's the same thesis
                        for et in existing_entry['theses']:
                            if et['thesis_name'] == nt['thesis_name']:
                                et['company_type'] = nt['company_type']
    
    final_list = list(consolidated.values())
    output_file = "../CompanyList.json"
    
    # Ensure directory exists if needed (though it's parent)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_list, f, indent=2)
        
    print(f"\nWorkflow 1 Complete: Identified {len(final_list)} unique companies across {len(theses)} theses.")
    print(f"Results saved to {output_file}")

if __name__ == "__main__":
    asyncio.run(main())
