# -*- coding: utf-8 -*-
"""
Created on Thu Feb  5 20:56:37 2026

@author: Akshay Subramaniam

Claude-assisted python script to parse, filter and analyze the KV Kvizzing Group chat, and extract and compile questions and answers. 
"""

import re
from datetime import datetime
from pathlib import Path
import json
import os 

def parse_and_split_chat_log(input_file, output_dir, start_date=None, end_date=None, 
                             username=None, split_by='date'):
    """
    Filter chat log by date range and/or username, then split into files.
    
    Args:
        input_file: Path to chat log
        output_dir: Directory for output files
        start_date: Filter start date (datetime.date object)
        end_date: Filter end date (datetime.date object)
        username: Filter by specific username (case-insensitive)
        split_by: 'date' or 'user' - how to split output files
    """
    Path(output_dir).mkdir(exist_ok=True)
    
    messages = parse_messages(input_file)
    
    # Apply filters
    filtered = filter_messages(messages, start_date, end_date, username)
    
    # Split and save
    if split_by == 'date':
        split_by_date(filtered, output_dir)
    elif split_by == 'user':
        split_by_user(filtered, output_dir)
    else:
        # Save all to one file
        save_messages(f"{output_dir}/all_messages.txt", filtered)

def parse_messages(input_file):
    """Parse chat log into structured messages. Format: [9/23/25, 14:52:20] Username: message"""
    messages = []
    current_message = None
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            # Match format: [9/23/25, 14:52:20] Username: message for pure text 
            pattern_1 =  r'\u200e\[(\d{1,2}/\d{1,2}/\d{2}),\s+(\d{1,2}:\d{2}:\d{2})\]\s+([^:]+):\s*(.*)'
            pattern_2 =  r'\[(\d{1,2}/\d{1,2}/\d{2}),\s+(\d{1,2}:\d{2}:\d{2})\]\s+([^:]+):\s*(.*)'
                          
            #Check pattern 1 
            match  = re.match(pattern_1,line)

            if not match: 
             #Check pattern 2 
                match = re.match(pattern_2,line)
            
            if match:
                # Save previous message if exists
                if current_message:
                    messages.append(current_message)
                
                date_str, time_str, username, text = match.groups()
                timestamp = datetime.strptime(f"{date_str} {time_str}", '%m/%d/%y %H:%M:%S')
                
                current_message = {
                    'timestamp': timestamp,
                    'date': timestamp.date(),
                    'time': timestamp.time(),
                    'username': username.strip(),
                    'text': text.strip(),
                    'full_text': text.strip()
                }
            elif current_message and line.strip():
                # Multi-line message continuation
                current_message['full_text'] += '\n' + line.rstrip()
        
        # Don't forget the last message
        if current_message:
            messages.append(current_message)
    
    return messages

def filter_messages(messages, start_date=None, end_date=None, username=None):
    """Filter messages by date range and/or username."""
    filtered = messages
    
    if start_date:
        filtered = [m for m in filtered if m['date'] >= start_date]
    
    if end_date:
        filtered = [m for m in filtered if m['date'] <= end_date]
    
    if username:
        username_lower = username.lower()
        filtered = [m for m in filtered if username_lower in m['username'].lower()]
    
    return filtered

def split_by_date(messages, output_dir):
    """Split messages into files by date."""
    by_date = {}
    for msg in messages:
        date_key = msg['date']
        if date_key not in by_date:
            by_date[date_key] = []
        by_date[date_key].append(msg)
    
    for date, msgs in by_date.items():
        filename = f"{output_dir}/chat_{date.strftime('%Y-%m-%d')}.txt"
        save_messages(filename, msgs)

def split_by_user(messages, output_dir):
    """Split messages into files by username."""
    by_user = {}
    for msg in messages:
        username = msg['username']
        if username not in by_user:
            by_user[username] = []
        by_user[username].append(msg)
    
    for username, msgs in by_user.items():
        # Clean username for filename
        safe_username = re.sub(r'[^\w\-]', '_', username)
        filename = f"{output_dir}/chat_{safe_username}.txt"
        save_messages(filename, msgs)

def save_messages(filename, messages):
    """Save messages to file in original format."""
    with open(filename, 'w', encoding='utf-8') as f:
        for msg in messages:
            timestamp_str = msg['timestamp'].strftime('[%m/%d/%y, %H:%M:%S]')
            f.write(f"{timestamp_str} {msg['username']}: {msg['full_text']}\n")
    print(f"Saved {len(messages)} messages to {filename}")

def extract_qa_pairs(input_file, output_file, question_indicators=None, leading_indicators=None, answer_confirmations=None):
    """
    Extract question-answer pairs from chat log.
    
    Args:
        input_file: Path to filtered chat log
        output_file: Path for Q&A output (JSON format)
        question_indicators: List of question patterns (default: ?, what, how, why, etc.)
        leading_indicators: List of potential phrases that might lead to a question 
        answer_confirmations: List of patterns that confirm an answer
        
    """
    if question_indicators is None:
                 
        question_indicators = [
            r'\b(can|what|how|why|when|where|who|which|whose|whom).+\?', # Contains question mark
            r'\b(Can|What|How|Why|When|Where|Who|Which|Whose|Whom).+\?', # Contains question mark
            r'\b(Can|What|How|Why|When|Where|Who|Which|Whose|Whom).*\?',
            r'\b(can|what|how|why|when|where|who|which|whose|whom).*\?',
            r'\bconnect\b',
            r'\bI want\b',
            r'\b(Give|Identify|Id|ID|Tell|Show|Explain|Describe|List|Find|Provide|Name|Connect|FITB|Need|Want)\b',
            r'^\d+\.',
            r'\bQ+\.', # Beginning with number and period, and the letter Q and period.
            r'^Q+\d+\.',
            r'^Q+\d',
            r'\bNYTXW\b',
            r'\b__+\b', #Explicit blanks
            r'\bJust give\b', #Specific keywords to look for
            r'\bclue\b', 
            #image identifiers 
            r'\bID\b.*image omitted',  # "ID [image]"
            r'\bIdentify\b.*image omitted',
            r'\bName\b.*image omitted',
            r'\bGuess\b.*image omitted',
            r'image omitted.*\?',  # Image followed by question
            r'(What|Who|Where|When|Which|How).*image omitted',
            r'image omitted.*(What|Who|Where|Which)',
            r'^Q[:\.\)\s]\s*\d*',
            r'^Very easy\b',
            r'^Easy\b',
            r'^Alright and for the top tweet\b',
            r'^Bonus.*',
            r'\bSookha Poori\b',
            r'\bSukha Puri\b',
            r'^\bGuess\b',
            r'\d+\)',
            r'\bX1, X1, X1, X1\b',
            r'^Complete\b',
            r'\bOne from me\b',
            r'\bquick and easy one\b',
            r'\b can anyone identify\b',
            r'\bFUQ\b',
            r'^Another\b',
            r'^Probably a sitter\b',
            r'^Number\b',
            r'\bthe same title was included in the\b',
            r'\bon the buzzer\b',
            r'^Question\b',
            r'\bStarting with a breezy one\b',
            r'\bHere is the question\b'
        ]
    if answer_confirmations is None:
        answer_confirmations = [
            r'\bis correct\b',
            r'\bcorrect\b',
            r'^It is\b',
            r'\bit is$',
            r'\bit is\b',
            r'\bis right\b',
            r'\bis the right answer\b',
            r'\bis the correct answer\b',
            r'\bthat\'?s correct\b',
            r'\bthat\'?s right\b',
            r'\byes,?\s+(that\'?s|it\'?s)?\s*(correct|right)\b',
            r'\bexactly\b',
            r'\bthe answer is\b',
            r'\byes+\b',  # Matches 'yes', 'yess', 'yesss', etc.
            r'^yes+$',    # Matches messages that are just 'yes', 'yess', etc.
            r'^Yes+$',
            r'\btechnically\b',
            r'\bX is\b',
            r'\bY is \b',
            r'\bX= \b',
            r'\bY = \b',
            r'\bX=\b',
            r'\bY=\b',
            r'\b.*is X$',
            r'\b.*is Y$',
            r'\b(Closed|closed)\b', #often used to indicate that a question has been correctly answered
            r'^Answer\b',
            r'^bingo\b',
            r'\bIt[\u0027\u2019]?s\b', #Catch different unicodes for apostrophe types 
            r'\bgreat crack\b',
            r'\bgets it\b',
            r'\bwill give it to you\b',
            r'\bwill give it\b',
            r'\bwill give some points\b',
            r'\bwill give points\b',
            r'^Correct\b',
            r'^Ding ding ding.*$',
            r'\bis the answer\b',
            r'\band gone\b',
            r'^Too quick\b.',
            r'\bhave cracked the funda\b',
            r'\bcracks the funda\b',
            r'\b(?:have\s+)?crack\w*\s+the\s+funda\b',
            r'^yup+\b',
            r'^yep+\b',
            r'\s*Yup\b.*',
            r'\bX - \b',
            r'\bY - \b',
            r'^Correcto\b',
            r'\bSuper crack\b',
            r'^Beautiful\b',
            r'^perfect\b', 
            r'\bwill close\b',
            r'^Closing\b',
            r'^💯\b',
            r'^Yeah\b',
            r'^That[\u0027\u2019]?s\b',
            r'^That is\b', 
            r'^I[\u0027\u2019]?ll give some pts to\b',
            r'\bclosing this\b',
            r'\bthat[\u0027\u2019]?s it\b',
            r'\bne de diya answer\b', 
            r'\bCorrrect\b',
            r'^Correct.*',
            r'\bI even removed the hint\b',
            r'\b^Spot on\b',
            r'\bsahi hai\b',
            r'\banswer sahi hai\b',
            r'\bbhaawnaayein samajh li thi par haan puraa naam dedena\b',
            r'^This is the\b',
            r'\bin particular\b',
        ]
    #Define leading indicators for questions, this is also an optional argument
    if leading_indicators is None: 
        leading_indicators=[r'^Next\b',
                            r'\s*Next Q\b.*',
                            r'^next question\b',
                            r'^Next question\b',
                            r'^OK next',
                            r'^Ok next',
                            r'\bmoving onto next\b',
                            r'^Last one\b',
                            r'^Last Q\.*',
                            r'\s*Very easy Q so hands on buzzers\.*',
                            r'^Trial Ball\b',
                            r'^Ye bohot easy hai so hands on buzzers\b',
                            r'^hands on buzzer.*',
                            r'^FFF.*',
                            r'^First one coming up\b',
                            r'^Number\b',
                            r'\s*One more\b',
                            r'^Okay first\b',
                            r'^ek aur hai\b',
                            r'^Okay, first Q\b',
                            r'\bI have a question\b',
                            r'\bfirst q\b',
                            r'\bI can start mine now\b',
                            r'^Starting\b'
        ]

    
    messages = parse_messages(input_file)
    qa_pairs = []

    # Initialize used leading indicators - if a message does not match a question indicator, we will still search for leading indicators in its vicinity 
    used_leading_indicators = set()
    i=0 #Initialize counter

    #initialize next_question indicators 
    next_question_flag = 0
    is_next_question = False
    
    print(len(messages))
    while i < len(messages):
    #for i, msg in enumerate(messages):
        msg = messages[i]
        text = msg['full_text']

        
        # Check if this looks like a question or request
        is_question = any(re.search(pattern, text, re.DOTALL | re.MULTILINE) for pattern in question_indicators)

        # If the question lacks indicators, back up and check for leading indicators in previous n messages
        if not is_question: 
            n_search_range = 5
            for k in range(i-1,i-1-n_search_range,-1):
                if k in used_leading_indicators: 
                    continue
                prev_msg = messages[k]
                prev_text = prev_msg['full_text']
                prev_user = prev_msg['username']
                #print(f"k={k}, user={prev_user}, text={repr(prev_text)}")
                #print(f"user match: {prev_user == msg['username']}")
                if(prev_user==msg['username']):
                    found_indicator = any(re.search(pattern,prev_text) for pattern in leading_indicators)
                    if found_indicator:
                        is_question = True
                        used_leading_indicators.add(k) # Matched the indicator with the question, so it has been 'exhausted' 
                        break
                    
        if is_question:
            # Look for answers and confirmations in following messages (from ANY user)
            answers = []
            confirmed_answers_struct=[]
            question_asker = msg['username'] #The name of the question asker is recorded
            confirmed_answers=None
            j = i + 1 # Default to next message if look-ahead range is empty
            # Enter the question context Check next several messages for potential answers and confirmations
            for j in range(i + 1, min(i + 15, len(messages))):  # Look ahead up to 49 messages
                next_msg = messages[j]
                next_text = next_msg['full_text']

                # Check if another question starts (will begin the next Q&A context)
                if(next_question_flag==0 and j>i+1):
                    is_next_question = any(re.search(pattern, next_text) 
                                        for pattern in question_indicators)
                    #if is_next_question and j > i + 1:
                        #continue
                    if not is_next_question: 
                        n_search_range = 5
                        for k in range(i,i-n_search_range,-1):
                            if k in used_leading_indicators: 
                                continue
                            prev_msg = messages[k]
                            prev_text = prev_msg['full_text']
                            prev_user = prev_msg['username']
                #print(f"k={k}, user={prev_user}, text={repr(prev_text)}")
                #print(f"user match: {prev_user == msg['username']}")
                            if(prev_user==msg['username']):
                                found_indicator = any(re.search(pattern,prev_text) for pattern in leading_indicators)
                            if found_indicator:
                                is_next_question = True
                                used_leading_indicators.add(k) # Matched the indicator with the question, so it has been 'exhausted' 
                                break
                    if is_next_question:
                        next_question_flag = 1
                        next_question_index = j
                else:
                    pass
                

                # Check if this message contains answer confirmation phrases
                if (next_msg['username']==question_asker):
                    has_confirmation = any(re.search(pattern, next_text,re.IGNORECASE) 
                                      for pattern in answer_confirmations)
                    if has_confirmation:
                        # Look backwards to find the answer being confirmed
                        # It's usually the messages right before the confirmation and from a different user. So we will record n messages before the confirmations 
                        confirmed_answers = []
                        answer_counter = 0
                        n_answer_search = 5
                        if answers:
                            for answer_test in answers[-n_answer_search:]:
                                answer_counter+=1
                                confirmed_answer = answer_test  # Most recent answer before confirmation
                                confirmed_answers.append({
                                'timestamp': confirmed_answer['timestamp'],
                                'username': confirmed_answer['username'],
                                'text': confirmed_answer['text'],
                                'confidence': 'high'})
                                if(answer_counter>n_answer_search):
                                    #confirmed_answers=reversed(confirmed_answers) #Need to do this to fix chronology
                                    break
                            confirmed_answers_struct.append([confirmed_answers,{'confirmation': next_msg}])
                            #print(confirmed_answers_struct)
                               
                        #break
                    else:
                    # Asker is likely discussing the question further, offering hints and feedback    
                        answers.append({
                            'timestamp': next_msg['timestamp'].isoformat(),
                            'username': next_msg['username'],
                            'text': next_msg['full_text'],
                            'confidence': 'normal',
                            'confirmation': 'feedback/hint/confirmation'})
                else:
                    # This is a potential answer
                    answers.append({
                        'timestamp': next_msg['timestamp'].isoformat(),
                        'username': next_msg['username'],
                        'text': next_msg['full_text'],
                        'confidence': 'normal',
                        'confirmation': 'possible answer'
                        })
                
                
                
                
        


            
            # Use confirmed answers if found, otherwise only list potential answers 
            final_answers = confirmed_answers_struct if confirmed_answers else None
            qa_pairs.append({
                'question': {
                    'timestamp': msg['timestamp'].isoformat(),
                    'username': msg['username'],
                    'text': msg['full_text']
                },
                'answer': final_answers,
                'all_answers': answers if len(answers) > 1 else None  # Include all answers if multiple attempts
            })
            
            if is_next_question:
                i=next_question_index
                next_question_flag=0 #reset the flag
                is_next_question = False
            else:
                i = max(i+1,j)
                print(i)
        else:
            i=i+1
    
    # Save as JSON
    #with open(output_file, 'w', encoding='utf-8') as f:
        #json.dump(qa_pairs, f, indent=2, ensure_ascii=False)
    
    print(f"Extracted {len(qa_pairs)} Q&A pairs to {output_file}")
    
    # Also save human-readable format
    txt_output = output_file.replace('.json', '.txt')
    with open(txt_output, 'w', encoding='utf-8') as f:
        for i, pair in enumerate(qa_pairs, 1):
            f.write(f"*** Potential Q&A Pair {i} ***\n")
            f.write(f"Q [{pair['question']['timestamp']}] {pair['question']['username']}:\n")
            f.write(f"  {pair['question']['text']}\n\n")
            
            if pair['answer']:
                answers = pair['answer']
                for answers00 in answers:
                    answers0 = answers00[0]
                    answer_confirmation=answers00[1]
                    for answer in answers0:  
                        confidence_marker = " ✓✓" if answer['confidence'] == 'high' else ""
                        if(answer['username']==pair['question']['username']):
                            f.write(f"Feedback [{answer['timestamp']}] {answer['username']}:")
                            f.write(f"  {answer['text']}\n")
                        else:
                            f.write(f"A [{answer['timestamp']}] {answer['username']}:")
                            f.write(f"  {answer['text']}\n")

                    if answer_confirmation['confirmation']:
                        f.write(f"\n Possible answer confirmation [{answer_confirmation['confirmation']['timestamp']}] {answer_confirmation['confirmation']['username']}:\n")
                        f.write(f"  {answer_confirmation['confirmation']['text']}\n")
            
            
                # Show all attempts and confirmations if there were multiple, this helps us catch part answers and multiple answers, for example
                if pair['all_answers'] and len(pair['all_answers'])>1:
                    f.write(f"\n  [Question context: {len(pair['all_answers']) - 1}]\n")
                    for attempt in pair['all_answers']:
                            if attempt['confidence']=='high':
                                confidence_marker = " ✓✓" 
                            f.write(f" {attempt['confirmation']}   - [{attempt['timestamp']}] {attempt['username']}: {attempt['text'][:500]}..\n")
                            #Write confirmation 
                            #f.write(f"\n Potential confirmation   - [{attempt['confirmation']['timestamp']}] {attempt['confirmation']['username']}:\n")
                            #f.write(f"  {attempt['confirmation']['text']}\n") 

                """ if pair['all_answers'] and len(pair['all_answers']) > 1:
                    f.write(f"\n  [Question context: {len(pair['all_answers']) - 1}]\n")
                    for attempt in pair['all_answers']:
                        if attempt != answer:
                            if attempt['confidence']!='high':
                                f.write(f" {attempt['confirmation']}   - [{attempt['timestamp']}] {attempt['username']}: {attempt['text'][:500]}..\n") """
            else:
                f.write("A: [No explicit confirmation detected]\n")
                # Show all attempts if there were multiple
                if pair['all_answers'] and len(pair['all_answers']) > 1:
                    f.write(f"\n  [Question context: {len(pair['all_answers']) - 1}]\n")
                    for attempt in pair['all_answers']:
                            f.write(f" {attempt['confirmation']}   - [{attempt['timestamp']}] {attempt['username']}: {attempt['text'][:500]}..\n")
            f.write("\n" + "="*50 + "\n\n")
    
    print(f"Saved human-readable format to {txt_output}")
    
    # Print statistics
    high_conf = sum(len(pair['answer']) for pair in qa_pairs if pair['answer'])
    with_answers = sum(1 for pair in qa_pairs if pair['answer'])
    multiple_attempts = sum(1 for pair in qa_pairs if pair.get('all_answers') and len(pair['all_answers']) > 1)
    
    print(f"Questions with answers: {with_answers}/{len(qa_pairs)}")
    print(f"High confidence answers: {high_conf}/{with_answers if with_answers > 0 else len(qa_pairs)}")
    print(f"Questions with multiple attempts: {multiple_attempts}")
    
    return qa_pairs


# Example usage:
if __name__ == "__main__":
    # Example 1: Filter by username and split by date
    #parse_and_split_chat_log(
        #'_chat.txt', 
        #'output_Akshay', 
        #username='~',
        #split_by='date'
    #)
    
    # Example 2: Filter by date range
    start = datetime(2025, 9, 23).date()
    end = datetime(2026, 3, 18).date()
    parse_and_split_chat_log('_chat.txt', 'output_all', start, end)
    
    # Example 3: Split by user (all users, separate files)
    # parse_and_split_chat_log('chat.log', 'output_by_user', split_by='user')
    
    # Example 4: Extract Q&A pairs from filtered chat
    #parse_and_split_chat_log(
         #'_chat.txt',
         #'temp_filtered',
         #split_by='date'
    #)
    
    # Then extract Q&A pairs
current_dir = '.'
output_dir = 'extracted_qa_pairs/'
source_dir = 'output_all'
full_source_path = os.path.join(current_dir,source_dir)
print(full_source_path)
for file_name in os.listdir(full_source_path):
    full_file_path = os.path.join(full_source_path,file_name)
    if os.path.isfile(full_file_path):
        base_name = file_name.split('.txt')[0]
        output_file_name = base_name+'_qa_pairs.txt'
        print(output_file_name)
        full_dest_path  = os.path.join(current_dir,output_dir)
        full_output_path = os.path.join(full_dest_path,output_file_name)
        extract_flag = extract_qa_pairs(full_file_path,full_output_path)
            



#aaa =  extract_qa_pairs('_chat.txt','output_all/all.txt')

