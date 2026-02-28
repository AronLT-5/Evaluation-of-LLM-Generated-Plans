# Run `humaneval50_batch_v2` - `humaneval` / `HumanEval/126`

- Plans found: 12
- Expected for complete task: 12

## Task Text

```text
[DATASET] humaneval
[TASK_ID] HumanEval/126

[PRIMARY_TASK]

def is_sorted(lst):
    '''
    Given a list of numbers, return whether or not they are sorted
    in ascending order. If list has more than 1 duplicate of the same
    number, return False. Assume no negative numbers and only integers.

    Examples
    is_sorted([5]) ➞ True
    is_sorted([1, 2, 3, 4, 5]) ➞ True
    is_sorted([1, 3, 2, 4, 5]) ➞ False
    is_sorted([1, 2, 3, 4, 5, 6]) ➞ True
    is_sorted([1, 2, 3, 4, 5, 6, 7]) ➞ True
    is_sorted([1, 3, 2, 4, 5, 6, 7]) ➞ False
    is_sorted([1, 2, 2, 3, 3, 4]) ➞ True
    is_sorted([1, 2, 2, 2, 3, 4]) ➞ False
    '''


[CONTEXT_FIELDS]
entry_point:
is_sorted

task_id:
HumanEval/126
```

## Plans

### Batch 1 / Plan 1 (humaneval:HumanEval/126:humaneval50_batch_v2:b1:p1)
- Strategy: Type-Driven
- Unique Step: Analyze input types and constraints

Steps:
- [1] Identify the input type as a list of integers
  Rationale: Understanding the input type helps determine appropriate operations and checks
  Checks:
  - Input is a list
  - Elements are integers
- [2] Determine the properties to check: ascending order and duplicate counts
  Rationale: The function must verify sorting and duplicate constraints to meet requirements
- [3] Plan to iterate through the list comparing adjacent elements
  Rationale: Comparing adjacent elements is a direct way to verify ascending order
- [4] Plan to count occurrences of each number to detect duplicates exceeding two
  Rationale: Counting duplicates ensures the function returns False if any number appears more than twice

### Batch 1 / Plan 2 (humaneval:HumanEval/126:humaneval50_batch_v2:b1:p2)
- Strategy: Complexity-Guardrails
- Unique Step: Optimize checks to maintain linear time complexity

Steps:
- [1] Plan a single pass through the list to check sorting and count duplicates simultaneously
  Rationale: Combining checks in one pass improves efficiency and meets performance expectations
- [2] Use a dictionary or hashmap to track counts of each number during iteration
  Rationale: Efficient counting of duplicates requires constant time updates per element
- [3] At each step, verify current element is not less than previous to ensure ascending order
  Rationale: Early detection of unsorted elements can short-circuit processing
- [4] If any number's count exceeds two, immediately return False to avoid unnecessary processing
  Rationale: Guardrails prevent wasted computation once failure condition is met

### Batch 1 / Plan 3 (humaneval:HumanEval/126:humaneval50_batch_v2:b1:p3)
- Strategy: Test-Design-Mental
- Unique Step: Design test cases covering edge and typical scenarios

Steps:
- [1] Identify edge cases such as empty list and single-element list
  Rationale: Edge cases ensure function handles minimal inputs correctly
- [2] Include tests with strictly ascending lists without duplicates
  Rationale: Validates basic sorting functionality
- [3] Include tests with duplicates appearing once and twice
  Rationale: Checks correct handling of allowed duplicates
- [4] Include tests with duplicates appearing more than twice and unsorted lists
  Rationale: Ensures function correctly returns False for invalid inputs

### Batch 1 / Plan 4 (humaneval:HumanEval/126:humaneval50_batch_v2:b1:p4)
- Strategy: Failure-Modes-First
- Unique Step: Identify and handle failure conditions early

Steps:
- [1] Check if the list is empty or has one element and return True immediately
  Rationale: These cases are trivially sorted and meet requirements
- [2] Iterate through the list to detect any descending order violation
  Rationale: Detecting unsorted elements early prevents unnecessary further checks
- [3] Track counts of each number and return False if any count exceeds two
  Rationale: Early failure on duplicate count violation improves efficiency
- [4] If no failure conditions are met, return True indicating the list is sorted and valid
  Rationale: Completes the function logic by confirming all conditions are satisfied

### Batch 2 / Plan 1 (humaneval:HumanEval/126:humaneval50_batch_v2:b2:p1)
- Strategy: Minimal-Solution-First
- Unique Step: Implement a single pass check for sorting and duplicates

Steps:
- [1] Implement a function to iterate through the list once
  Rationale: A single pass can efficiently check both sorting and duplicate conditions
  Checks:
  - Function iterates over the list exactly once
- [2] During iteration, check if current element is less than previous
  Rationale: If any element is less than the previous, list is not sorted ascending
  Checks:
  - Detect any descending order in the list
- [3] Count occurrences of each element during iteration
  Rationale: To detect if any element appears more than twice, which invalidates the list
  Checks:
  - Track frequency of elements
- [4] If any element occurs more than twice, return False
  Rationale: More than one duplicate of the same number is not allowed
  Checks:
  - Return False if frequency > 2
- [5] Return True if list is sorted and no element occurs more than twice
  Rationale: All conditions for a valid sorted list with allowed duplicates are met
  Checks:
  - Return True when all conditions satisfied

### Batch 2 / Plan 2 (humaneval:HumanEval/126:humaneval50_batch_v2:b2:p2)
- Strategy: Spec-First
- Unique Step: Analyze specification details and constraints

Steps:
- [1] Read the function specification carefully
  Rationale: Understanding requirements is essential before implementation
  Checks:
  - Specification is fully understood
- [2] Identify that list must be sorted in ascending order
  Rationale: Sorting order is the primary condition to check
  Checks:
  - Sorting order is ascending
- [3] Note the condition about duplicates: more than one duplicate is disallowed
  Rationale: Duplicates allowed only once, more than that returns False
  Checks:
  - Duplicates count constraint understood
- [4] Recognize assumptions: no negative numbers and only integers
  Rationale: Simplifies input validation and edge case considerations
  Checks:
  - Assumptions are noted
- [5] Plan to implement checks for sorting and duplicate counts accordingly
  Rationale: Implementation must reflect all specification points
  Checks:
  - Implementation plan aligns with spec

### Batch 2 / Plan 3 (humaneval:HumanEval/126:humaneval50_batch_v2:b2:p3)
- Strategy: Examples-First
- Unique Step: Use provided examples to understand expected behavior

Steps:
- [1] Review all given examples in the docstring
  Rationale: Examples illustrate how the function should behave in different cases
  Checks:
  - All examples are reviewed
- [2] Analyze examples where list is sorted and duplicates are allowed once
  Rationale: Examples like [1,2,2,3,3,4] show allowed duplicates
  Checks:
  - Understand allowed duplicate cases
- [3] Analyze examples where list is not sorted or duplicates exceed one
  Rationale: Examples like [1,3,2,4,5] and [1,2,2,2,3,4] show failure cases
  Checks:
  - Understand failure cases
- [4] Derive rules from examples to implement checks
  Rationale: Examples guide the logic for sorting and duplicate validation
  Checks:
  - Rules derived from examples
- [5] Plan to implement function to satisfy all example outputs
  Rationale: Ensures correctness and completeness
  Checks:
  - Implementation matches example outputs

### Batch 2 / Plan 4 (humaneval:HumanEval/126:humaneval50_batch_v2:b2:p4)
- Strategy: Edge-Cases-First
- Unique Step: Identify and plan for edge cases based on problem constraints

Steps:
- [1] Consider edge case of empty list and single element list
  Rationale: These are minimal inputs and should return True
  Checks:
  - Empty and single element lists handled
- [2] Consider edge case of list with all identical elements
  Rationale: More than one duplicate of the same number should return False
  Checks:
  - Detect multiple duplicates in identical elements
- [3] Consider edge case of list with duplicates exactly once
  Rationale: Duplicates allowed once should return True
  Checks:
  - Allow one duplicate per element
- [4] Consider edge case of list with descending order or unsorted elements
  Rationale: Should return False if not sorted ascending
  Checks:
  - Detect unsorted lists
- [5] Plan to implement checks that cover these edge cases explicitly
  Rationale: Ensures robustness and correctness of the function
  Checks:
  - Edge cases covered by implementation

### Batch 3 / Plan 1 (humaneval:HumanEval/126:humaneval50_batch_v2:b3:p1)
- Strategy: Invariants-First
- Unique Step: Identify invariants about sortedness and duplicates

Steps:
- [1] Define the invariant that the list must be non-decreasing
  Rationale: A sorted list in ascending order means each element is less than or equal to the next
  Checks:
  - Invariant correctly represents ascending order
- [2] Define the invariant that no element appears more than twice
  Rationale: The problem states that more than one duplicate (i.e., more than two occurrences) invalidates the list
  Checks:
  - Invariant correctly limits duplicates to at most two occurrences
- [3] Check the list for ascending order by verifying each element is <= the next
  Rationale: To confirm the sortedness invariant holds for the entire list
  Checks:
  - All adjacent pairs satisfy the order condition
- [4] Count occurrences of each number and verify none exceed two
  Rationale: To enforce the duplicate constraint invariant
  Checks:
  - No number appears more than twice

### Batch 3 / Plan 2 (humaneval:HumanEval/126:humaneval50_batch_v2:b3:p2)
- Strategy: Pseudocode-First
- Unique Step: Write detailed pseudocode before implementation

Steps:
- [1] Write pseudocode to iterate through the list and check ascending order
  Rationale: Clarifies the logic for verifying sortedness
  Checks:
  - Pseudocode correctly iterates and compares elements
- [2] Write pseudocode to count duplicates and check if any number appears more than twice
  Rationale: Ensures the duplicate constraint is handled explicitly
  Checks:
  - Pseudocode correctly counts and compares occurrences
- [3] Combine the two checks in pseudocode to return False if either condition fails
  Rationale: Integrates both conditions into a single decision process
  Checks:
  - Pseudocode returns correct boolean based on checks
- [4] Outline edge cases in pseudocode such as single-element lists and empty lists
  Rationale: Ensures robustness and correctness for all input sizes
  Checks:
  - Edge cases are handled explicitly in pseudocode

### Batch 3 / Plan 3 (humaneval:HumanEval/126:humaneval50_batch_v2:b3:p3)
- Strategy: Decompose-Then-Solve
- Unique Step: Break down the problem into sortedness check and duplicate count

Steps:
- [1] Decompose the problem into two subproblems: checking ascending order and checking duplicates
  Rationale: Simplifies the problem into manageable parts
  Checks:
  - Decomposition covers all problem requirements
- [2] Implement a function to verify the list is sorted in ascending order
  Rationale: Isolates the sortedness logic for clarity and reuse
  Checks:
  - Function correctly identifies sorted lists
- [3] Implement a function to count occurrences and verify no number appears more than twice
  Rationale: Separates duplicate checking logic for modularity
  Checks:
  - Function correctly counts and validates duplicates
- [4] Combine results of the two functions to determine the final return value
  Rationale: Ensures both conditions are met before returning True
  Checks:
  - Final output is True only if both conditions hold

### Batch 3 / Plan 4 (humaneval:HumanEval/126:humaneval50_batch_v2:b3:p4)
- Strategy: Brute-Force-Then-Optimize
- Unique Step: Start with a straightforward approach then refine for efficiency

Steps:
- [1] Implement a brute-force check for sortedness by comparing each element to the next
  Rationale: Simple initial approach to verify ascending order
  Checks:
  - Correctness of brute-force sortedness check
- [2] Implement a brute-force count of each element's occurrences using a dictionary or map
  Rationale: Straightforward way to detect duplicates exceeding two
  Checks:
  - Correctness of brute-force duplicate counting
- [3] Combine both brute-force checks to return False if either condition fails
  Rationale: Ensures correctness before optimization
  Checks:
  - Combined logic returns correct boolean
- [4] Analyze and optimize by reducing redundant passes over the list, e.g., checking sortedness and counting duplicates in a single pass
  Rationale: Improves efficiency while maintaining correctness
  Checks:
  - Optimized approach produces same results as brute-force
