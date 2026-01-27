# Liminal Demo Flow Plan - Methodical Testing

This plan outlines a step-by-step, methodical approach to testing the complete Liminal demo flow. **Each phase must complete before moving to the next** - wait for AI responses and verify functionality before proceeding.

## Testing Principles

1. **One Feature at a Time**: Test each feature completely before moving to the next
2. **Wait for Responses**: Always wait for AI responses to complete before taking next action
3. **Verify Functionality**: Check backend logs if something doesn't work as expected
4. **Clean State**: Start fresh for each major phase if needed
5. **Document Issues**: Note any bugs or unexpected behavior for fixes

---

## Phase 1: Exploration & Goal Discovery (Complete First)

### Actions
1. **Start Fresh Session**
   - Navigate to `http://localhost:5173`
   - Login with new username (e.g., `demo_user_fresh`)
   - Wait for exploration chat to load

2. **Exploration Conversation**
   - Type: "I'm a software developer interested in learning about neural networks and building AI applications. I understand the basics but want to really grasp how backpropagation works and how models learn from data."
   - **WAIT** for AI response (15-20 seconds)
   - Continue conversation if needed: "I think the mathematical foundations are what I'm most uncertain about."
   - **WAIT** for AI response

3. **Goal Acceptance**
   - **VERIFY**: Goal appears in sidebar with status "Ready"
   - Click on goal to accept
   - **WAIT** for goal chat to load

### Expected Results
- ✅ Goal appears in sidebar
- ✅ Feed panel shows relevant articles
- ✅ Learner Profile panel updates
- ✅ Goal chat opens successfully

### Verification
- Check sidebar for goal
- Check Feed panel for articles
- Check Learner Profile for understanding markers

---

## Phase 2: Goal Chat & Teaching Topics (Wait for Completion)

### Actions
1. **Continue Goal Chat Conversation**
   - Type: "I'm particularly confused about how the chain rule applies in backpropagation. I understand it from calculus, but I'm not sure how it connects to updating weights in a neural network."
   - **WAIT** for AI response (15-20 seconds)
   - **DO NOT** proceed until response is complete

2. **Verify Teaching Topics**
   - **CHECK**: Teaching topic appears in sidebar (e.g., "how the chain rule applies in backpropagation")
   - **VERIFY**: Status is "Ready"
   - Note the teaching topic for later testing

### Expected Results
- ✅ AI responds to question
- ✅ Teaching topic appears in sidebar
- ✅ Learner Profile updates with new concepts

### Verification
- Check sidebar for teaching topics
- Check Learner Profile for concept knowledge updates
- Wait for "Analyzing..." to complete

---

## Phase 3: Curriculum Generation (Complete Before Modification)

### Actions
1. **Generate Learning Path**
   - Click "Generate Learning Path" button
   - **WAIT** for curriculum generation (25-30 seconds)
   - **DO NOT** proceed until curriculum appears

2. **Verify Curriculum Display**
   - **CHECK**: Curriculum tasks appear in UI component (not in chat message)
   - **CHECK**: Tasks are numbered and have descriptions
   - **CHECK**: First task shows "available", others show "locked"
   - **CHECK**: Accept and Modify buttons are visible
   - **VERIFY**: No raw JSON in chat

### Expected Results
- ✅ Curriculum appears in nice UI component
- ✅ 8-12 tasks are displayed
- ✅ Tasks are properly formatted
- ✅ No duplicate display (not in chat + UI)

### Verification
- Check that curriculum UI component is visible
- Check that chat message is simple (not full curriculum text)
- Verify task statuses (available/locked)

---

## Phase 4: Curriculum Modification (CRITICAL - Test Thoroughly)

### Actions
1. **Click Modify Button**
   - Click "Modify" button on curriculum
   - **WAIT** for input field to appear (if applicable)
   - If no input field, use the goal chat input

2. **Send Modification Request**
   - Type: "Can we skip the basics and focus more on practical implementation? I'd like to jump straight into building a neural network from scratch."
   - Submit the message
   - **WAIT** for AI response (20-30 seconds)
   - **DO NOT** proceed until response is complete

3. **Verify Modification Applied**
   - **CHECK**: New curriculum appears (should replace old one)
   - **CHECK**: First task should be "Building a Simple Neural Network from Scratch" or similar
   - **CHECK**: Basic/intro tasks should be removed or moved later
   - **VERIFY**: Curriculum reflects the modification request

4. **Check Backend Logs**
   - Run: `tail -100 backend.log | grep -i "modify\|negotiate\|curriculum"`
   - **VERIFY**: Logs show curriculum regeneration
   - **VERIFY**: Modification request is being processed
   - Note any errors or warnings

### Expected Results
- ✅ AI processes modification request
- ✅ New curriculum is generated
- ✅ New curriculum reflects user's request (skip basics, focus on practical)
- ✅ Backend logs show curriculum regeneration

### Verification
- Compare old vs new curriculum tasks
- Check that modification is actually applied (not just same curriculum)
- Verify backend logs show negotiation/regeneration

### If Modification Doesn't Work
- Check backend logs for errors
- Verify `negotiate_curriculum` mode is being set
- Check if `propose_task_curriculum` action is triggered
- Review interviewer.py for curriculum regeneration logic

---

## Phase 5: Context Integration (After Modification Complete)

### Actions
1. **Navigate to Context Tab**
   - Click "Context" tab
   - **WAIT** for context panel to load

2. **Add Context**
   - Type: "Here's a code snippet showing a simple neural network forward pass:

```python
def forward_pass(inputs, weights, bias):
    output = np.dot(inputs, weights) + bias
    return sigmoid(output)
```

This is the basic structure I'm working with."
   - Click "Add Context" button
   - **WAIT** for context to be saved (2-3 seconds)

3. **Verify Context Added**
   - **CHECK**: Context appears in context panel
   - **CHECK**: Token count is displayed
   - **VERIFY**: Context is saved

4. **Test Context Usage**
   - Return to goal chat
   - Type: "How would I modify the forward_pass function I shared to add backpropagation? Can you explain it using the code I provided?"
   - **WAIT** for AI response (15-20 seconds)
   - **VERIFY**: AI response references the context code

### Expected Results
- ✅ Context is added successfully
- ✅ Context appears in panel
- ✅ AI references context in response
- ✅ Context persists across conversation

### Verification
- Check context panel for added item
- Check AI response for references to the code snippet
- Verify context is being used in AI responses

---

## Phase 6: Document Creation & AI Suggestions

### Actions
1. **Navigate to Documents Tab**
   - Click "Documents" tab
   - **WAIT** for documents panel to load

2. **Create Document**
   - Type document title: "Backpropagation Notes"
   - Click "+" button to create
   - **WAIT** for document editor to load

3. **Add Content**
   - Type: "Backpropagation is a key algorithm for training neural networks. It uses the chain rule to compute gradients. The gradients are used to update weights. This helps the network learn from data."
   - **WAIT** for auto-save (2 seconds)
   - **WAIT** for auto-suggestions to appear (5-10 seconds)

4. **Verify Auto-Suggestions**
   - **CHECK**: "Analyzing..." indicator appears
   - **WAIT** for suggestions to appear
   - **VERIFY**: Suggestions are concise and direct (not verbose)

5. **Test Manual Feedback**
   - Click "Get AI Feedback" button
   - **WAIT** for feedback to appear (10-15 seconds)
   - **VERIFY**: Feedback is personalized and helpful

### Expected Results
- ✅ Document is created successfully
- ✅ Auto-suggestions appear while typing
- ✅ Suggestions are concise and actionable
- ✅ Manual feedback works
- ✅ Document version increments correctly (not continuously)

### Verification
- Check document version number (should increment only on content changes)
- Check for auto-suggestions
- Verify suggestions are not too verbose
- Test "Get AI Feedback" button

---

## Phase 7: Terminal Activity & Claude Code

### Actions
1. **Navigate to Terminal Tab**
   - Click "Terminal" tab
   - **WAIT** for terminal to connect

2. **Create Project Folder**
   - Type: `mkdir backpropagation-demo && cd backpropagation-demo`
   - Press Enter
   - **WAIT** for command to complete
   - **VERIFY**: Terminal shows new prompt

3. **Use Claude Code**
   - Type: `claude code create a simple neural network implementation in Python that demonstrates backpropagation`
   - Press Enter
   - **WAIT** for Claude Code to generate files
   - **VERIFY**: Files are created

4. **Verify AI Observation**
   - **CHECK**: AI suggestion appears in terminal or goal chat
   - **WAIT** for AI to observe terminal activity
   - **VERIFY**: AI provides personalized explanation
   - **CHECK**: Explanation references learning goal and context

5. **Test Command Completion Detection**
   - Run a simple command: `ls -la`
   - **WAIT** for command to complete
   - **VERIFY**: `command_complete` message is sent
   - **CHECK**: AI observes the command

### Expected Results
- ✅ Terminal connects successfully
- ✅ Commands execute correctly
- ✅ Claude Code generates files
- ✅ AI observes terminal activity
- ✅ AI suggestions appear with personalized explanations
- ✅ Command completion is detected

### Verification
- Check terminal output (no ANSI escape sequences)
- Check for AI suggestion banners
- Verify explanations are personalized
- Check backend logs for `command_complete` messages

---

## Phase 8: Teaching Topic Selection

### Actions
1. **Select Teaching Topic**
   - Go back to goal chat
   - Click on a teaching topic in sidebar (e.g., "how the chain rule applies in backpropagation")
   - **WAIT** for teaching session to start

2. **Verify Teaching Session**
   - **CHECK**: Teaching session begins
   - **VERIFY**: AI provides focused teaching on the topic
   - **CHECK**: Learning is personalized to user's level

### Expected Results
- ✅ Teaching topic can be selected
- ✅ Teaching session begins
- ✅ AI provides focused teaching
- ✅ Learning is personalized

### Verification
- Check that clicking teaching topic starts a session
- Verify teaching is focused on the selected topic
- Check that learning is personalized

---

## Phase 9: Return to Exploration & New Goal Creation

### Actions
1. **Navigate to Exploration**
   - Click "Exploration" in sidebar
   - **WAIT** for exploration chat to load

2. **Continue Exploration Conversation**
   - Type about a different interest (e.g., "I'm also interested in learning about machine learning deployment and MLOps")
   - **WAIT** for AI response
   - Continue conversation until new goal appears

3. **Verify New Goal Creation**
   - **CHECK**: New goal appears in sidebar
   - **VERIFY**: Goal is different from first goal
   - **CHECK**: Can click on new goal to start learning

### Expected Results
- ✅ User can return to exploration
- ✅ New goal is created from conversation
- ✅ Multiple goals can exist simultaneously
- ✅ Each goal has its own learning path

### Verification
- Check sidebar for multiple goals
- Verify new goal is created
- Check that goals are independent

---

## Phase 10: Teaching Candidate Selection (During Exploration)

### Actions
1. **Observe Teaching Candidates**
   - During exploration conversation, watch sidebar
   - **WAIT** for teaching candidates to appear
   - **VERIFY**: Candidates appear as conversation progresses

2. **Select Teaching Candidate**
   - Click on a teaching candidate in sidebar
   - **WAIT** for teaching session to start
   - **VERIFY**: Can start learning immediately without full curriculum

### Expected Results
- ✅ Teaching candidates appear during exploration
- ✅ Candidates can be selected directly
- ✅ Learning can start immediately from candidate
- ✅ No need to generate full curriculum first

### Verification
- Check sidebar for teaching candidates during exploration
- Verify clicking candidate starts teaching
- Check that this is an alternative to curriculum-first approach

---

## Testing Checklist

### Before Starting Demo Flow
- [ ] Backend is running (`http://localhost:8000`)
- [ ] Frontend is running (`http://localhost:5173`)
- [ ] All recent fixes are applied
- [ ] Backend logs are accessible

### Phase 1: Exploration
- [ ] User can login
- [ ] Exploration chat works
- [ ] Goal appears in sidebar
- [ ] Feed panel populates

### Phase 2: Goal Chat
- [ ] Goal chat opens
- [ ] Conversation works
- [ ] Teaching topics appear
- [ ] Learner Profile updates

### Phase 3: Curriculum Generation
- [ ] Curriculum generates successfully
- [ ] Tasks display in UI component (not chat)
- [ ] Tasks are properly formatted
- [ ] Accept/Modify buttons work

### Phase 4: Curriculum Modification ⚠️ CRITICAL
- [ ] Modify button works
- [ ] Modification request is sent
- [ ] **WAIT** for AI response
- [ ] New curriculum is generated
- [ ] Modification is actually applied
- [ ] Backend logs show regeneration
- [ ] No errors in logs

### Phase 5: Context
- [ ] Context tab works
- [ ] Context can be added
- [ ] Context appears in panel
- [ ] AI references context in responses

### Phase 6: Documents
- [ ] Documents tab works
- [ ] Documents can be created
- [ ] Auto-suggestions appear
- [ ] Manual feedback works
- [ ] Version tracking works correctly

### Phase 7: Terminal
- [ ] Terminal connects
- [ ] Commands execute
- [ ] Claude Code works
- [ ] AI observes activity
- [ ] Suggestions appear
- [ ] No ANSI escape sequences in output

### Phase 8: Teaching Topics
- [ ] Teaching topics can be selected
- [ ] Teaching session starts
- [ ] Learning is personalized

### Phase 9: New Goal Creation
- [ ] Can return to exploration
- [ ] New goal is created
- [ ] Multiple goals work

### Phase 10: Teaching Candidates
- [ ] Candidates appear during exploration
- [ ] Candidates can be selected
- [ ] Immediate learning works

---

## Important Notes

1. **Always Wait**: Don't proceed to next step until current step is complete
2. **Check Logs**: If something doesn't work, check backend logs immediately
3. **One Thing at a Time**: Don't test multiple features simultaneously
4. **Verify Results**: Always verify expected results before moving on
5. **Document Issues**: Note any bugs or unexpected behavior

---

## Backend Log Commands for Debugging

```bash
# Check for curriculum modification
tail -200 backend.log | grep -i "modify\|negotiate\|curriculum\|propose_task"

# Check for WebSocket messages
tail -200 backend.log | grep -i "websocket\|task_curriculum"

# Check for errors
tail -200 backend.log | grep -i "error\|exception\|traceback"

# Check orchestrator activity
tail -500 backend.log | grep -E "\[ORCHESTRATOR\]|\[INTERVIEWER\]"
```

---

## Next Steps

1. Start with Phase 1 (Exploration) - complete fully
2. Move to Phase 2 (Goal Chat) - wait for teaching topics
3. **Phase 3 (Curriculum) - generate and verify display**
4. **Phase 4 (Modification) - test thoroughly, check logs, wait for response**
5. Then proceed to Phase 5 (Context) - after modification is verified
6. Continue methodically through remaining phases
