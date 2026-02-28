# Run `humaneval50_batch_v2` - `humaneval` / `HumanEval/120`

- Plans found: 12
- Expected for complete task: 12

## Task Text

```text
[DATASET] humaneval
[TASK_ID] HumanEval/120

[PRIMARY_TASK]

def maximum(arr, k):
    """
    Given an array arr of integers and a positive integer k, return a sorted list 
    of length k with the maximum k numbers in arr.

    Example 1:

        Input: arr = [-3, -4, 5], k = 3
        Output: [-4, -3, 5]

    Example 2:

        Input: arr = [4, -4, 4], k = 2
        Output: [4, 4]

    Example 3:

        Input: arr = [-3, 2, 1, 2, -1, -2, 1], k = 1
        Output: [2]

    Note:
        1. The length of the array will be in the range of [1, 1000].
        2. The elements in the array will be in the range of [-1000, 1000].
        3. 0 <= k <= len(arr)
    """


[CONTEXT_FIELDS]
entry_point:
maximum

task_id:
HumanEval/120
```

## Plans

### Batch 1 / Plan 1 (humaneval:HumanEval/120:humaneval50_batch_v2:b1:p1)
- Strategy: Spec-First
- Unique Step: Understand the problem specification thoroughly

Steps:
- [1] Read and analyze the function specification and docstring
  Rationale: Understanding the problem requirements is essential to implement the correct logic
  Checks:
  - Ensure comprehension of input types and output format
- [2] Identify input constraints and output requirements
  Rationale: Constraints guide the implementation details and edge case handling
  Checks:
  - Check array length and element range constraints
  - Verify k range constraints
- [3] Plan the approach to find the maximum k elements and sort them
  Rationale: A clear approach ensures efficient and correct implementation
  Checks:
  - Confirm approach aligns with specification
- [4] Outline the steps to implement the function according to the specification
  Rationale: Breaking down the implementation into steps helps in systematic coding
  Checks:
  - Steps cover sorting and slicing the array

### Batch 1 / Plan 2 (humaneval:HumanEval/120:humaneval50_batch_v2:b1:p2)
- Strategy: Examples-First
- Unique Step: Analyze provided examples to infer requirements

Steps:
- [1] Examine each example input and output pair
  Rationale: Examples illustrate expected behavior and edge cases
  Checks:
  - Verify output length matches k
  - Check output is sorted
- [2] Identify patterns in the examples regarding sorting and selection
  Rationale: Patterns help deduce the algorithm needed
  Checks:
  - Confirm output contains the largest k elements
- [3] Derive the expected function behavior from examples
  Rationale: Behavior inference guides implementation
  Checks:
  - Ensure behavior matches all examples
- [4] Plan implementation steps based on example analysis
  Rationale: Implementation should satisfy all example cases
  Checks:
  - Plan includes sorting and selecting top k elements

### Batch 1 / Plan 3 (humaneval:HumanEval/120:humaneval50_batch_v2:b1:p3)
- Strategy: Edge-Cases-First
- Unique Step: Identify and analyze edge cases before implementation

Steps:
- [1] Consider minimum and maximum values of k (0 and len(arr))
  Rationale: Edge values of k test boundary conditions
  Checks:
  - k=0 returns empty list
  - k=len(arr) returns sorted full array
- [2] Consider arrays with duplicate values
  Rationale: Duplicates affect selection and sorting behavior
  Checks:
  - Output includes duplicates correctly
- [3] Consider arrays with negative and positive integers
  Rationale: Handling negative values correctly is important
  Checks:
  - Output correctly includes negative values when among top k
- [4] Plan implementation to handle identified edge cases
  Rationale: Ensuring correctness for edge cases improves robustness
  Checks:
  - Implementation covers all edge cases

### Batch 1 / Plan 4 (humaneval:HumanEval/120:humaneval50_batch_v2:b1:p4)
- Strategy: Invariants-First
- Unique Step: Determine invariants that must hold true throughout the function

Steps:
- [1] Identify that output length must always be k
  Rationale: Output size invariant ensures correct result size
  Checks:
  - Output length equals k
- [2] Identify that output list must be sorted in ascending order
  Rationale: Sorting invariant ensures output format consistency
  Checks:
  - Output is sorted ascending
- [3] Identify that output elements must be among the largest k elements in input
  Rationale: Selection invariant ensures correctness of chosen elements
  Checks:
  - All output elements are in input
  - No larger elements excluded
- [4] Plan implementation steps to maintain these invariants
  Rationale: Maintaining invariants guarantees correct and consistent output
  Checks:
  - Implementation respects all invariants

### Batch 2 / Plan 1 (humaneval:HumanEval/120:humaneval50_batch_v2:b2:p1)
- Strategy: Pseudocode-First
- Unique Step: Write pseudocode before implementation

Steps:
- [1] Write pseudocode outlining the approach to find the maximum k numbers
  Rationale: Pseudocode helps clarify the logic before coding
  Checks:
  - Pseudocode covers sorting and selecting top k elements
  Substeps:
    - [1.1] Describe sorting the array in ascending order
      Rationale: Sorting is necessary to identify the largest elements easily
    - [1.2] Describe selecting the last k elements from the sorted array
      Rationale: The last k elements after sorting ascending are the largest k elements
    - [1.3] Describe returning the selected elements as the result
      Rationale: Returning the selected elements completes the function
- [2] Translate the pseudocode into Python code
  Rationale: Implementing the plan in code is the next step
  Checks:
  - Code correctly sorts and slices the array
- [3] Test the function with example inputs
  Rationale: Testing verifies correctness of the implementation
  Checks:
  - Output matches expected results for given examples
- [4] Handle edge cases such as k=0 or k equals array length
  Rationale: Ensuring robustness for all valid inputs
  Checks:
  - Function returns empty list if k=0
  - Function returns sorted array if k equals length of arr

### Batch 2 / Plan 2 (humaneval:HumanEval/120:humaneval50_batch_v2:b2:p2)
- Strategy: Decompose-Then-Solve
- Unique Step: Break down the problem into smaller subproblems

Steps:
- [1] Identify subproblems: sorting the array and selecting top k elements
  Rationale: Decomposing simplifies the problem into manageable parts
  Checks:
  - Subproblems cover all aspects of the task
- [2] Implement sorting subproblem to sort the array in ascending order
  Rationale: Sorting is a prerequisite for selecting maximum elements
  Checks:
  - Array is sorted correctly
- [3] Implement selection subproblem to extract last k elements from sorted array
  Rationale: Selecting last k elements yields the maximum k numbers
  Checks:
  - Selection returns correct elements
- [4] Combine sorting and selection to form the complete solution
  Rationale: Combining subproblems solves the original task
  Checks:
  - Combined function returns correct sorted list of maximum k numbers

### Batch 2 / Plan 3 (humaneval:HumanEval/120:humaneval50_batch_v2:b2:p3)
- Strategy: Brute-Force-Then-Optimize
- Unique Step: Start with a simple brute-force approach then optimize

Steps:
- [1] Implement brute-force approach by sorting the entire array
  Rationale: Sorting the entire array is a straightforward way to find maximum elements
  Checks:
  - Array is sorted correctly
- [2] Select the last k elements from the sorted array
  Rationale: Last k elements are the largest after sorting
  Checks:
  - Correct elements are selected
- [3] Return the selected elements as the result
  Rationale: Returning completes the brute-force solution
  Checks:
  - Output matches expected results
- [4] Consider optimization by using a heap to find k largest elements if needed
  Rationale: Heap can improve efficiency for large arrays and small k
  Checks:
  - Heap approach returns correct results

### Batch 2 / Plan 4 (humaneval:HumanEval/120:humaneval50_batch_v2:b2:p4)
- Strategy: Type-Driven
- Unique Step: Use type information to guide implementation

Steps:
- [1] Analyze input types: arr as list of integers, k as integer
  Rationale: Understanding input types helps determine valid operations
  Checks:
  - Types are correctly identified
- [2] Determine output type: list of integers of length k
  Rationale: Output type guides the structure of the return value
  Checks:
  - Output is a list of integers
- [3] Use sorting function applicable to list of integers
  Rationale: Sorting requires input to be a list of comparable elements
  Checks:
  - Sorting function works on arr
- [4] Slice sorted list to length k ensuring output type matches
  Rationale: Slicing maintains list type and length constraints
  Checks:
  - Sliced list length equals k

### Batch 3 / Plan 1 (humaneval:HumanEval/120:humaneval50_batch_v2:b3:p1)
- Strategy: Complexity-Guardrails
- Unique Step: limit input size and validate k

Steps:
- [1] Check if k is within the valid range 0 to length of arr
  Rationale: Ensures the function handles edge cases and invalid inputs gracefully
  Checks:
  - k >= 0
  - k <= len(arr)
- [2] Limit the input array size to a maximum of 1000 elements
  Rationale: Prevents performance issues and respects problem constraints
  Checks:
  - len(arr) <= 1000
- [3] Sort the array to prepare for selecting maximum elements
  Rationale: Sorting simplifies extracting the largest k elements
  Checks:
  - arr is sorted
- [4] Select the last k elements from the sorted array and return them
  Rationale: The last k elements in a sorted array are the maximum k elements
  Checks:
  - result length == k
  - result is sorted

### Batch 3 / Plan 2 (humaneval:HumanEval/120:humaneval50_batch_v2:b3:p2)
- Strategy: Test-Design-Mental
- Unique Step: design tests before implementation

Steps:
- [1] Design test cases covering edge cases like k=0, k=len(arr), and negative numbers
  Rationale: Ensures the function handles all input scenarios correctly
  Checks:
  - test cases cover edge conditions
- [2] Design test cases with duplicate maximum values
  Rationale: Validates correct handling of duplicates in the output
  Checks:
  - test cases include duplicates
- [3] Design test cases with all negative numbers
  Rationale: Checks function correctness with negative values
  Checks:
  - test cases include negative numbers
- [4] Design test cases with mixed positive and negative numbers
  Rationale: Ensures function works with varied input
  Checks:
  - test cases include mixed sign numbers

### Batch 3 / Plan 3 (humaneval:HumanEval/120:humaneval50_batch_v2:b3:p3)
- Strategy: Failure-Modes-First
- Unique Step: identify and handle failure modes

Steps:
- [1] Identify failure mode when k is zero
  Rationale: Function should return an empty list in this case
  Checks:
  - k == 0 returns []
- [2] Identify failure mode when k is greater than length of arr
  Rationale: Function should handle or reject invalid k values
  Checks:
  - k <= len(arr)
- [3] Identify failure mode when arr contains duplicates
  Rationale: Ensure duplicates are handled correctly in the output
  Checks:
  - duplicates preserved in output if among max
- [4] Identify failure mode when arr contains negative numbers
  Rationale: Function should correctly select maximum values even if negative
  Checks:
  - negative numbers handled correctly

### Batch 3 / Plan 4 (humaneval:HumanEval/120:humaneval50_batch_v2:b3:p4)
- Strategy: Minimal-Solution-First
- Unique Step: implement minimal correct solution

Steps:
- [1] Sort the input array in ascending order
  Rationale: Sorting arr allows easy selection of maximum k elements
  Checks:
  - arr is sorted ascending
- [2] Slice the last k elements from the sorted array
  Rationale: The last k elements are the maximum values
  Checks:
  - length of slice is k
- [3] Return the sliced list as the result
  Rationale: Returns the required sorted list of maximum k elements
  Checks:
  - result length == k
  - result is sorted ascending
- [4] Handle edge case when k is zero by returning an empty list
  Rationale: Ensures correct output for zero k
  Checks:
  - k == 0 returns []
