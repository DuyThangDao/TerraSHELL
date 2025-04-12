import json
import os


with open('output.txt', 'w') as f:
    f.write('|Threat|Description|Data Flow|\n|---|---|---|\n')
for file_name in os.listdir('catalog'):
    if file_name.endswith('.json'):
        with open(os.path.join('catalog', file_name), 'r') as f:
            data = json.load(f)
            name, des, attackers, victims  = data['metadata']['ns:textName'], data['metadata']['ns:textReviewProblem'], data['security']['ns:hasAggressor'], data['context']['ns:hasAffectedComponent']
            name = name[5:]
            output = ''
            count = 1
            for victim in victims:
                victim = victim.replace('su:comp_', '')
                for attacker in attackers:
                    attacker = attacker.replace('su:comp_', '')
                    output += str(count) +'. ' + attacker + ' -> ' + victim + '; '
                    count += 1
            output = output[:-2]
            with open('output.txt', 'a', encoding='utf-8') as f:
                f.write(f'|{name}|{des}|{output}|\n')


