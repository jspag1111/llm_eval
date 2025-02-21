// static/js/main.js

/* 
    LLM Workflow Manager - main.js (Refactored for MULTI-TURN PROMPTS and Evaluation Display)
*/

function showAlert(type, message) {
    const alertHTML = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;
    const container = document.querySelector('.container');
    if (container) {
        container.insertAdjacentHTML('afterbegin', alertHTML);
        setTimeout(() => {
            const alert = bootstrap.Alert.getInstance(container.querySelector('.alert'));
            if (alert) alert.close();
        }, 5000);
    }
}

function escapeHTML(str) {
    if (typeof str !== 'string') return str;
    return str.replace(/[&<>'"]/g, function(tag) {
        const charsToReplace = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            "'": '&#39;',
            '"': '&quot;'
        };
        return charsToReplace[tag] || tag;
    });
}

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        let r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

async function postData(url, data) {
    try {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
        return await response.json();
    } catch (error) {
        console.error(`Error posting data to ${url}:`, error);
        showAlert("danger", `Error communicating with the server at ${url}.`);
    }
}

async function fetchData(url) {
    try {
        const response = await fetch(url);
        return await response.json();
    } catch (error) {
        console.error(`Error fetching data from ${url}:`, error);
        showAlert("danger", `Error fetching data from ${url}.`);
        return null;
    }
}

let functionCodeEditor = null;

/* ============================
   WORKFLOW CREATION
============================ */

async function createWorkflow() {
    const workflowName = document.getElementById("workflowName").value.trim();
    if (!workflowName) {
        showAlert("danger", "Please enter a workflow name.");
        return;
    }
    const data = await postData(`/projects/${projectId}/add_workflow`, { workflow_name: workflowName });
    if (data && data.status === "workflow_added") {
        showAlert("success", "Workflow created successfully.");
        window.location.href = `/projects/${projectId}/workflow/${data.workflow_id}`;
    } else {
        showAlert("danger", data.error || "Failed to create workflow.");
    }
}

/* ============================
   STEP MANAGEMENT
============================ */

async function showAddStepModal() {
    // Implement showing the modal for adding a step
    const modalEl = new bootstrap.Modal(document.getElementById('addStepModal'));
    modalEl.show();
}

async function addStep() {
    const title = document.getElementById("newStepTitle").value.trim();
    const description = document.getElementById("newStepDescription").value.trim();
    const inputs = document.getElementById("newStepInputs").value.trim();

    const data = await postData(`/projects/${projectId}/workflow/${workflowId}/add_step`, {
        title: title,
        description: description,
        inputs: inputs,
        calls: [] // Initialize with no calls; can be updated later
    });

    if (data.status === "step_added") {
        location.reload();
    } else {
        showAlert("danger", data.error || "Failed to add step.");
    }
}

async function saveStepEdits(stepId) {
    const titleElem = document.querySelector(`button[data-bs-target="#collapse-${stepId}"]`);
    const title = titleElem ? titleElem.textContent.trim() : "Untitled Step";

    const desc = document.getElementById(`step-desc-${stepId}`).value.trim();
    const inp = document.getElementById(`step-inputs-${stepId}`).value.trim();

    const workflowData = await fetchData(`/report/${projectId}/${workflowId}`);
    if (!workflowData) return;
    const stepData = workflowData.steps.find(s => s.step_id === stepId);
    const calls = stepData ? stepData.calls : [];

    const data = await postData(`/projects/${projectId}/workflow/${workflowId}/edit_step`, {
        step_id: stepId,
        title: title,
        description: desc,
        inputs: inp,
        calls: calls
    });

    if (data.status === "step_edited") {
        showAlert("success", "Step updated successfully.");
        window.location.reload();
    } else {
        showAlert("danger", data.error || "Failed to edit step.");
    }
}

async function removeStep(step_id) {
    if (!confirm("Are you sure you want to delete this step?")) return;
    const data = await postData(`/projects/${projectId}/workflow/${workflowId}/remove_step`, { step_id: step_id });
    if (data.status === "step_removed") {
        showAlert("success", "Step removed successfully.");
        window.location.reload();
    } else {
        showAlert("danger", data.error || "Failed to remove step.");
    }
}

document.addEventListener("DOMContentLoaded", function() {
    // ===========  STEPS & ACCORDION  =========== 
    const stepsList = document.getElementById("stepsAccordion");
    if (stepsList) {
        Sortable.create(stepsList, {
            animation: 150,
            onEnd: function () {
                const newOrder = Array.from(stepsList.children).map(li => li.getAttribute('data-step-id'));
                reorderSteps(newOrder);
            },
        });
    }

    // ===========  RESIZABLE SIDE PANEL  =========== 
    const dragHandle = document.getElementById("dragHandle");
    const splitContainer = document.getElementById("splitContainer");
    const leftPane = document.getElementById("leftPane");
    const rightPane = document.getElementById("rightPane");

    let isResizing = false;

    if (dragHandle && splitContainer && leftPane && rightPane) {
        dragHandle.addEventListener('mousedown', function(e) {
            isResizing = true;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', function(e) {
            if (!isResizing) return;
            const containerRect = splitContainer.getBoundingClientRect();
            let newWidth = containerRect.right - e.clientX;
            const maxWidth = containerRect.width * 0.8;
            const minWidth = 300;
            if (newWidth < minWidth) newWidth = minWidth;
            if (newWidth > maxWidth) newWidth = maxWidth;
            rightPane.style.flex = `0 0 ${newWidth}px`;
            leftPane.style.flex = `1 1 calc(100% - ${newWidth + 5}px)`;
        });

        document.addEventListener('mouseup', function() {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = 'default';
                document.body.style.userSelect = 'auto';
            }
        });
    }

    // ===========  RUN WORKFLOW BUTTON  ===========
    const runButton = document.getElementById("runWorkflowBtn");
    if (runButton) {
        runButton.addEventListener("click", runWorkflow);
    }

    // ===========  CALL loadEvaluations ON PAGE LOAD  ===========
    // This ensures that any existing evaluations for the project are
    // displayed immediately when the project_detail page loads.
    if (document.getElementById("evaluationsContainer")) {
        loadEvaluations();
    }
});

/* ============================
   REORDER STEPS
============================ */

async function reorderSteps(new_order) {
    const data = await postData(`/projects/${projectId}/workflow/${workflowId}/reorder_steps`, { new_order });
    if (data.status === "steps_reordered") {
        showAlert("success", "Steps reordered successfully.");
    } else {
        showAlert("danger", data.error || "Failed to reorder steps.");
    }
}


/* ============================
   COMMON VARIABLE NAMES MANAGEMENT
============================ */

/* ----------------------------
   Show Add Common Variable Name Modal
----------------------------- */
function showAddCommonVariableNameModal() {
    const addVarModal = new bootstrap.Modal(document.getElementById('addCommonVariableNameModal'));
    addVarModal.show();
}

/* ----------------------------
   Add Common Variable Name
----------------------------- */
async function addCommonVariableName() {
    const varName = document.getElementById("commonVarName").value.trim();

    if (!varName) {
        showAlert("danger", "Variable name is required.");
        return;
    }

    const data = await postData(`/projects/${projectId}/add_common_variable_name`, {
        var_name: varName
    });

    // Update the status check to match the server's response
    if (data && data.status === "common_variable_name_added") {
        const addVarModal = bootstrap.Modal.getInstance(document.getElementById('addCommonVariableNameModal'));
        if (addVarModal) addVarModal.hide();
        document.getElementById("addCommonVariableNameForm").reset();
        showAlert("success", `Variable '${varName}' added successfully.`);
        window.location.reload();
    } else {
        showAlert("danger", data.error || "Failed to add variable name.");
    }
}


/* ----------------------------
   Remove Common Variable Name
----------------------------- */
async function removeCommonVariableName(varName) {
    if (!confirm(`Are you sure you want to delete the variable '${varName}'?`)) return;

    const data = await postData(`/projects/${projectId}/remove_common_variable_name`, {
        var_name: varName
    });

    if (data && data.status === "common_variable_name_removed") {
        showAlert("success", `Variable '${varName}' removed successfully.`);
        window.location.reload();
    } else {
        showAlert("danger", data.error || "Failed to remove variable name.");
    }
}


/* ============================
   VARIABLE CRUD
============================ */

async function addVariable() {
    await handleEntity({ type: 'add_variable' });
}

async function editVariable(varName) {
    await handleEntity({ type: 'edit_variable', varName: varName });
}

async function removeVariable(varName) {
    await handleEntity({ type: 'remove_variable', varName: varName });
}

/* ============================
   GENERIC CRUD HANDLER
============================ */

async function handleEntity(options) {
    const { type, varName, callId, stepId } = options;
    switch (type) {
        case 'add_variable':
            const newVarName = document.getElementById("varName").value.trim();
            const newVarContent = document.getElementById("varContent").value.trim();
            if (!newVarName) {
                showAlert("danger", "Please enter a variable name.");
                return;
            }
            const addVarResponse = await postData(`/projects/${projectId}/workflow/${workflowId}/add_variable`, {
                var_name: newVarName,
                var_content: newVarContent
            });
            if (addVarResponse.status === "variable_added") {
                showAlert("success", `Variable '${newVarName}' added successfully.`);
                window.location.reload();
            } else {
                showAlert("danger", addVarResponse.error || "Failed to add variable.");
            }
            break;

        case 'edit_variable':
            const editedVarContent = document.getElementById(`content-${varName}`).value.trim();
            if (!editedVarContent) {
                showAlert("danger", "Variable content cannot be empty.");
                return;
            }
            const editVarResponse = await postData(`/projects/${projectId}/workflow/${workflowId}/edit_variable`, {
                var_name: varName,
                var_content: editedVarContent
            });
            if (editVarResponse.status === "variable_edited") {
                showAlert("success", `Variable '${varName}' updated successfully.`);
                window.location.reload();
            } else {
                showAlert("danger", editVarResponse.error || "Failed to edit variable.");
            }
            break;

        case 'remove_variable':
            if (!confirm(`Are you sure you want to delete the variable '${varName}'?`)) return;
            const removeVarResponse = await postData(`/projects/${projectId}/workflow/${workflowId}/remove_variable`, { var_name: varName });
            if (removeVarResponse.status === "variable_removed") {
                showAlert("success", `Variable '${varName}' removed successfully.`);
                window.location.reload();
            } else {
                showAlert("danger", removeVarResponse.error || "Failed to remove variable.");
            }
            break;

        case 'add_llm_call':
        case 'edit_llm_call': {
            const title = document.getElementById("llmCallTitle").value.trim();
            const systemPrompt = document.getElementById("llmSystemPrompt").value.trim();
            const variableName = document.getElementById("llmVariableName").value.trim();
            let variables;
            try {
                variables = JSON.parse(document.getElementById("llmVariables").value || "{}");
            } catch (err) {
                showAlert("danger", "Invalid JSON in Variables field.");
                return;
            }
            const outputFormat = document.getElementById("llmOutputFormat").value;
            const modelName = document.getElementById("llmModelName").value;
            const temperature = parseFloat(document.getElementById("llmTemperature").value);
            const maxTokens = parseInt(document.getElementById("llmMaxTokens").value);
            const topP = parseFloat(document.getElementById("llmTopP").value);

            // NEW: Pydantic & Retries
            let pydanticDefinition = "";
            let maxRetries = 0;
            if (outputFormat === "json") {
                pydanticDefinition = document.getElementById("llmPydanticDefinition").value.trim();
                maxRetries = parseInt(document.getElementById("llmMaxRetries").value) || 0;
            }

            // Build conversation from DOM
            const conversationContainer = document.getElementById("conversationContainer");
            const messageDivs = conversationContainer.querySelectorAll(".conversation-message");
            let conversation = [];
            messageDivs.forEach(div => {
                const roleSelect = div.querySelector(".conv-role");
                const contentTextarea = div.querySelector(".conv-content");
                if (roleSelect && contentTextarea) {
                    const msgRole = roleSelect.value;
                    const msgContent = contentTextarea.value.trim();
                    if (msgContent) {
                        conversation.push({ role: msgRole, content: msgContent });
                    }
                }
            });

            const workflowDataForCall = await fetchData(`/report/${projectId}/${workflowId}`);
            if (!workflowDataForCall) return;
            const stepObj = workflowDataForCall.steps.find(s => s.step_id === stepId);
            if (!stepObj) return;

            if (type === 'add_llm_call') {
                const newCallId = generateUUID();
                const newCall = {
                    call_id: newCallId,
                    title: title,
                    system_prompt: systemPrompt,
                    variable_name: variableName,
                    variables: variables,
                    model_name: modelName,
                    temperature: temperature,
                    max_tokens: maxTokens,
                    top_p: topP,
                    output_type: outputFormat,
                    conversation: conversation,
                    // NEW fields
                    pydantic_definition: pydanticDefinition || null,
                    max_retries: maxRetries || 0
                };
                stepObj.calls.push(newCall);
            } else if (type === 'edit_llm_call') {
                const existingCall = stepObj.calls.find(c => c.call_id === callId);
                if (!existingCall) {
                    showAlert("danger", "Could not find the existing call to edit.");
                    return;
                }
                existingCall.title = title;
                existingCall.system_prompt = systemPrompt;
                existingCall.variable_name = variableName;
                existingCall.variables = variables;
                existingCall.model_name = modelName;
                existingCall.temperature = temperature;
                existingCall.max_tokens = maxTokens;
                existingCall.top_p = topP;
                existingCall.output_type = outputFormat;
                existingCall.conversation = conversation;
                // NEW fields
                existingCall.pydantic_definition = pydanticDefinition || null;
                existingCall.max_retries = maxRetries || 0;
            }

            const postDataPayload = {
                step_id: stepObj.step_id,
                title: stepObj.title || "Untitled Step",
                description: stepObj.description || "",
                inputs: stepObj.inputs || "",
                calls: stepObj.calls
            };

            const saveCallResponse = await postData(`/projects/${projectId}/workflow/${workflowId}/edit_step`, postDataPayload);
            if (saveCallResponse.status === "step_edited") {
                showAlert("success", type === 'add_llm_call' ? "LLM call added successfully." : "LLM call edited successfully.");
                closeCallSidePanel();
                window.location.reload();
            } else {
                showAlert("danger", saveCallResponse.error || "Failed to save LLM call.");
            }
            break;
        }

        case 'remove_llm_call':
            if (!confirm("Are you sure you want to remove this LLM call?")) return;
            const workflowDataForRemoval = await fetchData(`/report/${projectId}/${workflowId}`);
            if (!workflowDataForRemoval) return;
            const stepObjForRemoval = workflowDataForRemoval.steps.find(s => s.step_id === stepId);
            if (!stepObjForRemoval) return;
            stepObjForRemoval.calls = stepObjForRemoval.calls.filter(c => c.call_id !== callId);

            const removeCallPayload = {
                step_id: stepObjForRemoval.step_id,
                title: stepObjForRemoval.title || "Untitled Step",
                description: stepObjForRemoval.description || "",
                inputs: stepObjForRemoval.inputs || "",
                calls: stepObjForRemoval.calls
            };

            const removeCallResponse = await postData(`/projects/${projectId}/workflow/${workflowId}/edit_step`, removeCallPayload);
            if (removeCallResponse.status === "step_edited") {
                showAlert("success", "LLM call removed successfully.");
                closeCallSidePanel();
                window.location.reload();
            } else {
                showAlert("danger", removeCallResponse.error || "Failed to remove LLM call.");
            }
            break;

        default:
            console.warn(`Unknown entity type: ${type}`);
    }
}

/* ============================
   LLM CALL Management
============================ */

function openCallSidePanel(stepId, callId = null) {
    const rightPane = document.getElementById("rightPane");
    const dragHandle = document.getElementById("dragHandle");

    rightPane.style.display = "block";
    rightPane.style.flex = "0 0 33.333%"; // default width
    dragHandle.style.display = "block";

    // Adjust leftPane's flex
    const leftPane = document.getElementById("leftPane");
    leftPane.style.flex = "1 1 calc(100% - 33.333% - 5px)";

    document.getElementById("llmCallForm").reset();
    document.getElementById("llmCallId").value = callId || "";
    document.getElementById("llmCallStepId").value = stepId;
    document.getElementById("llmRemoveCallBtn").style.display = callId ? "inline-block" : "none";

    // Clear conversation container
    const conversationContainer = document.getElementById("conversationContainer");
    conversationContainer.innerHTML = "";

    // **Activate the 'LLM Call Editor' tab**
    const llmTab = document.getElementById('llm-editor-tab');
    if (llmTab) {
        const tab = new bootstrap.Tab(llmTab);
        tab.show();
    }

    if (callId) {
        loadExistingCallData(stepId, callId);
    } else {
        // Defaults for new call
        document.getElementById("llmModelName").value = "gpt-4";
        document.getElementById("llmTemperature").value = "1";
        document.getElementById("llmMaxTokens").value = "1024";
        document.getElementById("llmTopP").value = "1.0";
        document.getElementById("llmOutputFormat").value = "text";
        document.getElementById("llmMaxRetries").value = "0";
        document.getElementById("llmPydanticDefinition").value = "";
        toggleJsonFields();
    }
}

function closeCallSidePanel() {
    const rightPane = document.getElementById("rightPane");
    const dragHandle = document.getElementById("dragHandle");
    const leftPane = document.getElementById("leftPane");

    rightPane.style.display = "none";
    rightPane.style.flex = "0 0 0%";
    dragHandle.style.display = "none";
    leftPane.style.flex = "1 1 100%";

    document.getElementById("llmCallForm").reset();
    document.getElementById("llmCallId").value = "";
    document.getElementById("llmCallStepId").value = "";
    document.getElementById("llmRemoveCallBtn").style.display = "none";

    // Clear conversation container
    const conversationContainer = document.getElementById("conversationContainer");
    conversationContainer.innerHTML = "";
}

async function loadExistingCallData(stepId, callId) {
    const workflowData = await fetchData(`/report/${projectId}/${workflowId}`);
    if (!workflowData) return;
    const stepData = workflowData.steps.find(s => s.step_id === stepId);
    if (!stepData) return;
    const callData = stepData.calls.find(c => c.call_id === callId);
    if (!callData) return;

    document.getElementById("llmCallTitle").value = callData.title || "";
    document.getElementById("llmSystemPrompt").value = callData.system_prompt || "";

    if (callData.variable_name) {
        document.getElementById("llmVariableName").value = callData.variable_name;
    } else {
        document.getElementById("llmVariableName").value = "";
    }
    
    let variablesJSON = {};
    if (callData.variables) {
        variablesJSON = JSON.parse(JSON.stringify(callData.variables));
    }
    document.getElementById("llmVariables").value = JSON.stringify(variablesJSON, null, 2);

    document.getElementById("llmModelName").value = callData.model_name || "gpt-4";
    document.getElementById("llmTemperature").value = callData.temperature || 1.0;
    document.getElementById("llmMaxTokens").value = callData.max_tokens || 1024;
    document.getElementById("llmTopP").value = callData.top_p || 1.0;
    document.getElementById("llmOutputFormat").value = callData.output_type || "text";

    // NEW: Populate pydantic_definition & max_retries if any
    const pydanticDefinitionSelect = document.getElementById("llmPydanticDefinition");
    const maxRetriesInput = document.getElementById("llmMaxRetries");

    if (callData.pydantic_definition) {
        // If the user had specified a model that is in the dropdown, select it
        // If not in the dropdown, we could optionally add it.
        pydanticDefinitionSelect.value = callData.pydantic_definition;
    } else {
        pydanticDefinitionSelect.value = "";
    }

    maxRetriesInput.value = callData.max_retries || 0;

    // Show/hide the pydantic & retry fields based on the format
    toggleJsonFields();

    // NEW MULTI-TURN: Rebuild conversation in the UI
    const conversationContainer = document.getElementById("conversationContainer");
    if (!conversationContainer) return;
    conversationContainer.innerHTML = "";

    if (callData.conversation && Array.isArray(callData.conversation)) {
        callData.conversation.forEach(msg => {
            const div = document.createElement("div");
            div.classList.add("conversation-message", "mb-2");
            div.innerHTML = `
                <div class="input-group">
                    <select class="form-select conv-role" style="max-width:80px;">
                        <option value="user" ${msg.role === "user" ? "selected" : ""}>User</option>
                        <option value="assistant" ${msg.role === "assistant" ? "selected" : ""}>Assistant</option>
                    </select>
                    <textarea class="form-control conv-content" rows="1" placeholder="Enter message...">${msg.content}</textarea>
                    <button class="btn btn-outline-danger" type="button" onclick="removeConversationMessage(this)">X</button>
                </div>
            `;
            conversationContainer.appendChild(div);
        });
    }
}

function addConversationMessage(role) {
    const conversationContainer = document.getElementById("conversationContainer");
    const div = document.createElement("div");
    div.classList.add("conversation-message", "mb-2");
    div.innerHTML = `
        <div class="input-group">
            <select class="form-select conv-role" style="max-width:80px;">
                <option value="user" ${role === "user" ? "selected" : ""}>User</option>
                <option value="assistant" ${role === "assistant" ? "selected" : ""}>Assistant</option>
            </select>
            <textarea class="form-control conv-content" rows="1" placeholder="Enter message..."></textarea>
            <button class="btn btn-outline-danger" type="button" onclick="removeConversationMessage(this)">X</button>
        </div>
    `;
    conversationContainer.appendChild(div);
}

function removeConversationMessage(button) {
    const parentDiv = button.closest(".conversation-message");
    if (parentDiv) {
        parentDiv.remove();
    }
}

function saveLLMCall() {
    const callId = document.getElementById("llmCallId").value;
    const type = callId ? 'edit_llm_call' : 'add_llm_call';
    const stepId = document.getElementById("llmCallStepId").value;

    handleEntity({ type, callId, stepId });
}

function removeLLMCall() {
    const callId = document.getElementById("llmCallId").value;
    const stepId = document.getElementById("llmCallStepId").value;
    if (!callId || !stepId) {
        showAlert("danger", "Cannot remove call: missing IDs.");
        return;
    }
    handleEntity({ type: 'remove_llm_call', callId, stepId });
}

document.addEventListener("DOMContentLoaded", async function() {
    // Existing code ...

    // ===========  LLM Output Format Toggles  ===========
    const outputFormatSelect = document.getElementById("llmOutputFormat");
    if (outputFormatSelect) {
        // On change, show/hide Pydantic & Retries fields
        outputFormatSelect.addEventListener("change", toggleJsonFields);
    }

    // NEW: fetch pydantic models and populate dropdown
    let pydanticModels = [];
    try {
        pydanticModels = await fetchPydanticModels();
    } catch (err) {
        console.error("Failed to fetch pydantic models:", err);
    }
    populatePydanticModelsDropdown(pydanticModels);
});

async function fetchPydanticModels() {
    // NEW: This function fetches the list of available Pydantic model names from the backend.
    // The backend must provide a route like GET /pydantic_models returning { "models": ["UserModel", "AnotherModel", ...] }
    const data = await fetchData("/pydantic_models");
    if (!data || !data.models) {
        console.warn("No pydantic models found or invalid response.");
        return [];
    }
    return data.models;
}

function populatePydanticModelsDropdown(models) {
    // Populates the #llmPydanticDefinition <select> with the given model names
    const select = document.getElementById("llmPydanticDefinition");
    if (!select) return;

    // Clear existing dynamic options, keeping only the default (None)
    select.querySelectorAll("option:not([value=''])").forEach(opt => opt.remove());

    // Add each model as an option
    models.forEach(model => {
        const option = document.createElement("option");
        option.value = model;
        option.textContent = model;
        select.appendChild(option);
    });
}

// Called when user changes the "Output Format" dropdown
function toggleJsonFields() {
    const outputFormatSelect = document.getElementById("llmOutputFormat");
    const pydanticContainer = document.getElementById("pydanticOptionsContainer");
    const retryContainer = document.getElementById("retryOptionsContainer");

    if (!outputFormatSelect || !pydanticContainer || !retryContainer) return;

    if (outputFormatSelect.value === "json") {
        pydanticContainer.style.display = "block";
        retryContainer.style.display = "block";
    } else {
        pydanticContainer.style.display = "none";
        retryContainer.style.display = "none";
    }
}


/* ============================
   RUN WORKFLOW
============================ */

// Initialize a guard variable to prevent multiple executions
let isWorkflowRunning = false;

// Event listener for the Run Workflow button
document.addEventListener("DOMContentLoaded", function() {
    const runButton = document.getElementById("runWorkflowBtn");
    if (runButton) {
        runButton.addEventListener("click", runWorkflow);
    }
});

async function runWorkflow() {
    const runButton = document.querySelector('button[onclick="runWorkflow()"]');
    if (runButton) runButton.disabled = true;

    const outputDiv = document.getElementById("workflowRunOutput");
    // Clear existing content before appending new results
    outputDiv.innerHTML = `
        <div class="d-flex align-items-center">
            <strong>Running workflow...</strong>
            <div class="spinner-border ms-auto" role="status" aria-hidden="true"></div>
        </div>
    `;

    const data = await postData(`/projects/${projectId}/workflow/${workflowId}/run`, { workflow_id: workflowId });
    if (runButton) runButton.disabled = false;

    if (data && data.status === "success") {
        // Clear the output div before appending new results
        outputDiv.innerHTML = ""; 

        let html = "<h4>Workflow Execution Results</h4>";
        const converter = new showdown.Converter();

        data.outputs.forEach((step, stepIndex) => {
            const stepId = `step-${step.step_id}`;
            html += `
                <div class="accordion mb-3" id="stepAccordion-${step.step_id}">
                    <div class="accordion-item">
                        <h2 class="accordion-header" id="heading-${stepId}">
                            <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-${stepId}" aria-expanded="false" aria-controls="collapse-${stepId}">
                                ${escapeHTML(step.step_title)}
                            </button>
                        </h2>
                        <div id="collapse-${stepId}" class="accordion-collapse collapse" aria-labelledby="heading-${stepId}" data-bs-parent="#stepAccordion-${step.step_id}">
                            <div class="accordion-body">
            `;
            if (step.calls && step.calls.length > 0) {
                
                step.calls.forEach((call, callIndex) => {
                    const callId = `call-${call.call_id}`;
                    html += `
                        <div class="accordion-item">
                            <h2 class="accordion-header" id="heading-call-${call.call_id}">
                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-call-${call.call_id}" aria-expanded="false" aria-controls="collapse-call-${call.call_id}">
                                    ${escapeHTML(call.title)} (${escapeHTML(call.model_name)})
                                </button>
                            </h2>
                            <div id="collapse-call-${call.call_id}" class="accordion-collapse collapse" aria-labelledby="heading-call-${call.call_id}" data-bs-parent="#callAccordion-${step.step_id}">
                                <div class="accordion-body">
                                    <div class="accordion mb-2" id="detailsAccordion-${call.call_id}">
                                        <div class="accordion-item">
                                            <h2 class="accordion-header" id="heading-system-${call.call_id}">
                                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-system-${call.call_id}" aria-expanded="false" aria-controls="collapse-system-${call.call_id}">
                                                    System Prompt
                                                </button>
                                            </h2>
                                            <div id="collapse-system-${call.call_id}" class="accordion-collapse collapse" aria-labelledby="heading-system-${call.call_id}" data-bs-parent="#detailsAccordion-${call.call_id}">
                                                <div class="accordion-body">
                                                    ${converter.makeHtml(escapeHTML(call.system_prompt))}
                                                </div>
                                            </div>
                                        </div>

                                        <!-- NEW: Conversation Display -->
                                        <div class="accordion-item">
                                            <h2 class="accordion-header" id="heading-conversation-${call.call_id}">
                                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-conversation-${call.call_id}" aria-expanded="false" aria-controls="collapse-conversation-${call.call_id}">
                                                    Conversation
                                                </button>
                                            </h2>
                                            <div id="collapse-conversation-${call.call_id}" class="accordion-collapse collapse" aria-labelledby="heading-conversation-${call.call_id}" data-bs-parent="#detailsAccordion-${call.call_id}">
                                                <div class="accordion-body">
                                                    ${formatConversation(call.conversation)}
                                                </div>
                                            </div>
                                        </div>

                                        <div class="accordion-item">
                                            <h2 class="accordion-header" id="heading-response-${call.call_id}">
                                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-response-${call.call_id}" aria-expanded="false" aria-controls="collapse-response-${call.call_id}">
                                                    Response
                                                </button>
                                            </h2>
                                            <div id="collapse-response-${call.call_id}" class="accordion-collapse collapse" aria-labelledby="heading-response-${call.call_id}" data-bs-parent="#detailsAccordion-${call.call_id}">
                                                <div class="accordion-body">
                                                    ${typeof call.response === 'object'
                                                        ? `<pre class='bg-light p-3 border rounded'>${JSON.stringify(call.response, null, 2)}</pre>`
                                                        : converter.makeHtml(escapeHTML(call.response))
                                                    }
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                });
                html += `</div>`;
            } else {
                html += `<p class="text-muted">No LLM calls in this step.</p>`;
            }

            // Add Function Calls
            if (step.functions && step.functions.length > 0) {
                html += `<h5>Function Calls</h5>`;
                html += `<div class="accordion mb-3" id="functionAccordion-${step.step_id}">`;
                step.functions.forEach((fn, fnIndex) => {
                    html += `
                        <div class="accordion-item">
                            <h2 class="accordion-header" id="heading-fn-${fn.call_id}">
                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-fn-${fn.call_id}" aria-expanded="false" aria-controls="collapse-fn-${fn.call_id}">
                                    ${escapeHTML(fn.title)}
                                </button>
                            </h2>
                            <div id="collapse-fn-${fn.call_id}" class="accordion-collapse collapse" aria-labelledby="heading-fn-${fn.call_id}" data-bs-parent="#functionAccordion-${step.step_id}">
                                <div class="accordion-body">
                                    <p><strong>Code:</strong></p>
                                    <pre class='bg-light p-3 border rounded'>${escapeHTML(fn.code)}</pre>
                                    <p><strong>Input Variables:</strong></p>
                                    <pre class='bg-light p-3 border rounded'>${escapeHTML(JSON.stringify(fn.input_variables, null, 2))}</pre>
                                    <p><strong>Output Variable:</strong> ${escapeHTML(fn.output_variable || "N/A")}</p>
                                    
                                    <div class="accordion mb-2" id="functionDetailsAccordion-${fn.call_id}">
                                        <div class="accordion-item">
                                            <h2 class="accordion-header" id="heading-fn-response-${fn.call_id}">
                                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-fn-response-${fn.call_id}" aria-expanded="false" aria-controls="collapse-fn-response-${fn.call_id}">
                                                    Response
                                                </button>
                                            </h2>
                                            <div id="collapse-fn-response-${fn.call_id}" class="accordion-collapse collapse" aria-labelledby="heading-fn-response-${fn.call_id}" data-bs-parent="#functionDetailsAccordion-${fn.call_id}">
                                                <div class="accordion-body">
                                                    ${typeof fn.response === 'object'
                                                        ? `<pre class='bg-light p-3 border rounded'>${JSON.stringify(fn.response, null, 2)}</pre>`
                                                        : escapeHTML(fn.response)
                                                    }
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                });
                html += `</div>`;
            } else {
                html += `<p class="text-muted">No function calls in this step.</p>`;
            }
    // Workflow Report

            html += `
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });

        // Evaluation Report
        html += "<h4>Evaluation Report</h4>";
        html += "<pre class='bg-light p-3 border rounded'>" + JSON.stringify(data.evaluation_report, null, 2) + "</pre>";

        outputDiv.innerHTML = html; // Set the innerHTML once after building the entire string
        showAlert("success", "Workflow executed successfully.");
    } else {
        outputDiv.innerHTML = "";
        showAlert("danger", data.error || "Failed to execute workflow.");
    }
}

/* ============================
   EVALUATIONS MANAGEMENT
============================ */

/* ----------------------------
   Load Evaluations on Page Load
----------------------------- */
async function loadEvaluations() {
    try {
        const response = await fetch(`/projects/${projectId}/evaluations`);
        const evaluations = await response.json();
        const container = document.getElementById('evaluationsContainer');
        if (!evaluations || evaluations.length === 0) {
            container.innerHTML = "<p class='text-muted'>No evaluations found.</p>";
            return;
        }

        let html = "<ul class='list-group'>";
        evaluations.forEach(ev => {
            html += `
                <li class='list-group-item'>
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${escapeHTML(ev.name)}</strong><br/>
                            <small>${escapeHTML(ev.description)}</small>
                        </div>
                        <div>
                            <button class='btn btn-sm btn-primary me-1' onclick='runEvaluation("${ev.evaluation_id}")'>Run</button>
                            <button class='btn btn-sm btn-secondary me-1' onclick='viewEvaluation("${ev.evaluation_id}")'>View Results</button>
                            <button class='btn btn-sm btn-danger' onclick='deleteEvaluation("${ev.evaluation_id}")'>Delete</button>
                        </div>
                    </div>
                </li>
            `;
        });
        html += "</ul>";
        container.innerHTML = html;
    } catch (error) {
        console.error("Load Evaluations Error:", error);
        showAlert('danger', 'Failed to load evaluations.');
    }
}

/* ----------------------------
   Show Add Evaluation Modal
----------------------------- */
function showAddEvaluationModal() {
    const modal = new bootstrap.Modal(document.getElementById('addEvaluationModal'));
    document.getElementById('addEvaluationForm').reset();
    document.getElementById('variableSetsContainer').innerHTML = "";
    addVariableSet(); // start with one set
    modal.show();
}



/* ----------------------------
   Add Variable Set to Evaluation Modal
----------------------------- */
/**
 * Handles uploading a JSON file containing variable sets.
 * Parses the file and stores the variable sets in a global variable.
 */
function uploadVariableSetsJson() {
    const fileInput = document.getElementById('uploadVariableSetsFile');
    if (!fileInput.files || !fileInput.files[0]) {
        showAlert("danger", "Please select a .json file to upload.");
        return;
    }

    const file = fileInput.files[0];
    const reader = new FileReader();

    reader.onload = function(e) {
        try {
            const parsed = JSON.parse(e.target.result);
            if (typeof parsed !== 'object' || Array.isArray(parsed)) {
                showAlert("danger", "Invalid JSON format. Expected a dictionary/object.");
                return;
            }

            // Store the parsed variable sets in a global variable
            window.uploadedVariableSets = parsed;

            // Optionally, display the uploaded variable sets for confirmation
            displayUploadedVariableSets(parsed);

            showAlert("success", "Variable sets uploaded successfully.");
        } catch(err) {
            showAlert("danger", "Error parsing JSON: " + err.message);
        }
    };

    reader.readAsText(file);
}

/**
 * Displays the uploaded variable sets within the modal for user confirmation.
 * @param {Object} variableSets - The parsed variable sets object.
 */
function displayUploadedVariableSets(variableSets) {
    const container = document.getElementById('variableSetsContainer');
    container.innerHTML = "<h5>Uploaded Variable Sets:</h5><ul class='list-group mb-3'></ul>";

    const list = container.querySelector('ul');

    for (const [id, vset] of Object.entries(variableSets)) {
        const listItem = document.createElement('li');
        listItem.className = "list-group-item";

        listItem.innerHTML = `
            <strong>Variable Set ID:</strong> ${escapeHTML(id)}<br/>
            <strong>Variables:</strong> <pre class="bg-light p-2">${escapeHTML(JSON.stringify(vset.variables, null, 2))}</pre>
            <strong>Ideal Output:</strong> ${escapeHTML(vset.ideal_output)}<br/>
            <strong>Number of Runs:</strong> ${escapeHTML(vset.num_runs)}
        `;
        list.appendChild(listItem);
    }
}

/**
 * Dynamically adds a new variable set input form for manual entry.
 */
function addVariableSet() {
    const container = document.getElementById('variableSetsContainer');
    const idx = container.querySelectorAll('.variable-set').length + 1;
    const html = `
    <div class="card variable-set mb-3">
        <div class="card-body">
            <h6>Variable Set #${idx}</h6>
            <div class="mb-3">
                <label class="form-label">Variables (JSON):</label>
                <textarea class="form-control var-variables" rows="3" placeholder='e.g., { "progress_note": "Patient is stable." }' required></textarea>
            </div>
            <div class="mb-3">
                <label class="form-label">Ideal Output:</label>
                <textarea class="form-control var-ideal" rows="2" placeholder='Describe the ideal output...'></textarea>
            </div>
            <div class="mb-3">
                <label class="form-label">Number of Runs:</label>
                <input type="number" class="form-control var-runs" value="1" min="1" required>
            </div>
            <button type="button" class="btn btn-sm btn-danger" onclick="removeVariableSet(this)">Remove Variable Set</button>
        </div>
    </div>`;
    container.insertAdjacentHTML('beforeend', html);
}

/**
 * Removes a manually added variable set form.
 * @param {HTMLElement} button - The remove button that was clicked.
 */
function removeVariableSet(button) {
    const card = button.closest('.variable-set');
    if (card) {
        card.remove();
    }
}

/**
 * Submits the evaluation with either uploaded or manually added variable sets.
 */
async function createEvaluation() {
    const name = document.getElementById('evalName').value.trim();
    const description = document.getElementById('evalDescription').value.trim();

    if (!name) {
        showAlert('danger', 'Evaluation name is required.');
        return;
    }

    let variableSets = {};

    // If variable sets were uploaded via JSON
    if (window.uploadedVariableSets && typeof window.uploadedVariableSets === 'object' && !Array.isArray(window.uploadedVariableSets)) {
        variableSets = window.uploadedVariableSets;
    } else {
        // Otherwise, collect manually added variable sets
        const sets = document.querySelectorAll('.variable-set');
        if (sets.length === 0) {
            showAlert('danger', 'Please add at least one variable set.');
            return;
        }

        // Assign unique IDs to each variable set manually
        sets.forEach((set, index) => {
            const varName = `manual_set_${index + 1}_${Date.now()}`; // Simple unique ID
            const variablesText = set.querySelector('.var-variables').value.trim();
            const idealOutput = set.querySelector('.var-ideal').value.trim();
            const numRuns = parseInt(set.querySelector('.var-runs').value);

            if (!variablesText) {
                showAlert('danger', `Variables are required for Variable Set #${index + 1}.`);
                throw new Error(`Variables are required for Variable Set #${index + 1}.`);
            }

            let variables = {};
            try {
                variables = JSON.parse(variablesText);
            } catch (err) {
                showAlert('danger', `Invalid JSON in Variable Set #${index + 1}: ${err.message}`);
                throw err;
            }

            variableSets[varName] = {
                variables: variables,
                ideal_output: idealOutput,
                num_runs: numRuns
            };
        });
    }

    const payload = {
        name: name,
        description: description,
        variable_sets: variableSets  // Now a dict with unique IDs as keys
    };

    try {
        const response = await fetch(`/projects/${projectId}/evaluations/create`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (data.status === "evaluation_created") {
            showAlert('success', 'Evaluation created successfully.');
            // Hide the modal
            const addEvaluationModal = bootstrap.Modal.getInstance(document.getElementById('addEvaluationModal'));
            if (addEvaluationModal) addEvaluationModal.hide();
            // Reset the form
            document.getElementById('addEvaluationForm').reset();
            document.getElementById('variableSetsContainer').innerHTML = "";
            window.uploadedVariableSets = {}; // Clear uploaded variable sets
            // Reload evaluations
            loadEvaluations();
        } else {
            showAlert('danger', data.error || 'Failed to create evaluation.');
        }
    } catch (error) {
        console.error("Create Evaluation Error:", error);
        showAlert('danger', 'An error occurred while creating the evaluation.');
    }
}

/* ----------------------------
   Create Evaluation
----------------------------- */
/**
 * Submits the evaluation with either uploaded or manually added variable sets.
 */
async function createEvaluation() {
    const name = document.getElementById('evalName').value.trim();
    const description = document.getElementById('evalDescription').value.trim();

    if (!name) {
        showAlert('danger', 'Evaluation name is required.');
        return;
    }

    let variableSets = {};

    // If variable sets were uploaded via JSON
    if (window.uploadedVariableSets && typeof window.uploadedVariableSets === 'object' && !Array.isArray(window.uploadedVariableSets)) {
        variableSets = window.uploadedVariableSets;
    } else {
        // Otherwise, collect manually added variable sets
        const sets = document.querySelectorAll('.variable-set');
        if (sets.length === 0) {
            showAlert('danger', 'Please add at least one variable set.');
            return;
        }

        // Assign unique IDs to each variable set manually
        sets.forEach((set, index) => {
            const varName = `manual_set_${index + 1}_${Date.now()}`; // Simple unique ID
            const variablesText = set.querySelector('.var-variables').value.trim();
            const idealOutput = set.querySelector('.var-ideal').value.trim();
            const numRuns = parseInt(set.querySelector('.var-runs').value);

            if (!variablesText) {
                showAlert('danger', `Variables are required for Variable Set #${index + 1}.`);
                throw new Error(`Variables are required for Variable Set #${index + 1}.`);
            }

            let variables = {};
            try {
                variables = JSON.parse(variablesText);
            } catch (err) {
                showAlert('danger', `Invalid JSON in Variable Set #${index + 1}: ${err.message}`);
                throw err;
            }

            variableSets[varName] = {
                variables: variables,
                ideal_output: idealOutput,
                num_runs: numRuns
            };
        });
    }

    const payload = {
        name: name,
        description: description,
        variable_sets: variableSets  // Now a dict with unique IDs as keys
    };

    try {
        const response = await fetch(`/projects/${projectId}/evaluations/create`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (data.status === "evaluation_created") {
            showAlert('success', 'Evaluation created successfully.');
            // Hide the modal
            const addEvaluationModal = bootstrap.Modal.getInstance(document.getElementById('addEvaluationModal'));
            if (addEvaluationModal) addEvaluationModal.hide();
            // Reset the form
            document.getElementById('addEvaluationForm').reset();
            document.getElementById('variableSetsContainer').innerHTML = "";
            window.uploadedVariableSets = {}; // Clear uploaded variable sets
            // Reload evaluations
            loadEvaluations();
        } else {
            showAlert('danger', data.error || 'Failed to create evaluation.');
        }
    } catch (error) {
        console.error("Create Evaluation Error:", error);
        showAlert('danger', 'An error occurred while creating the evaluation.');
    }
}

/* ----------------------------
   Delete Evaluation
----------------------------- */
async function deleteEvaluation(evaluationId) {
    if (!confirm("Are you sure you want to delete this evaluation?")) return;
    const data = await postData(`/projects/${projectId}/evaluations/${evaluationId}/delete`, {});
    if (data && data.status === "evaluation_deleted") {
        showAlert('success', 'Evaluation deleted successfully.');
        loadEvaluations();
    } else {
        showAlert('danger', data.error || 'Failed to delete evaluation.');
    }
}

/* ----------------------------
   Run Evaluation
----------------------------- */
async function runEvaluation(evaluationId) {
    if (!confirm("Running an evaluation may take some time. Continue?")) return;
    showAlert('info', 'Running evaluation, please wait...');
    const data = await postData(`/projects/${projectId}/evaluations/${evaluationId}/run`, {});
    if (data && data.status === "evaluation_run_complete") {
        showAlert('success', 'Evaluation run completed.');
        loadEvaluations();
    } else {
        showAlert('danger', data.error || 'Failed to run evaluation.');
    }
}

/* ----------------------------
   View Evaluation Results
----------------------------- */
async function viewEvaluation(evaluationId) {
    window.location.href = `/projects/${projectId}/evaluations/${evaluationId}/results`;
    const response = await fetch(`/projects/${projectId}/evaluations/${evaluationId}`);
    const ev = await response.json();
    if (ev.error) {
        showAlert('danger', ev.error);
        return;
    }

    const container = document.getElementById('evaluationResultsContainer');
    container.innerHTML = ""; // Clear previous content

    // Iterate through each workflow
    for (let [wf_id, wf_results] of Object.entries(ev.results)) {
        // Fetch workflow details for better readability
        const wf_data_response = await fetch(`/report/${projectId}/${wf_id}`);
        const wf_data = await wf_data_response.json();
        const wf_name = wf_data.name || wf_id;

        container.innerHTML += `
            <div class="mb-4">
                <h5>Workflow: ${escapeHTML(wf_name)}</h5>
                <div class="table-responsive">
                    <table class="table table-bordered">
                        <thead class="table-light">
                            <tr>
                                <th>Variable Set #</th>
                                <th>Run #</th>
                                <th>Match Score</th>
                                <th>Differences</th>
                                <th>Output</th>
                            </tr>
                        </thead>
                        <tbody>
        `;

        wf_results.forEach(result => {
            const var_set = ev.variable_sets[result.variable_set_index];
            container.innerHTML += `
                <tr>
                    <td>${result.variable_set_index + 1}</td>
                    <td>${result.run_index + 1}</td>
                    <td>${result.comparison.match_score}</td>
                    <td>
                        <pre style="max-height: 150px; overflow: auto;">${escapeHTML(result.comparison.differences)}</pre>
                    </td>
                    <td>
                        ${typeof result.output === 'object' 
                            ? `<pre style="max-height: 150px; overflow: auto;">${JSON.stringify(result.output, null, 2)}</pre>` 
                            : escapeHTML(result.output)}
                    </td>
                </tr>
            `;
        });

        container.innerHTML += `
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    // Update the modal title
    document.getElementById('viewEvaluationModalLabel').textContent = `Evaluation Results: ${ev.name}`;

    // Show the modal
    const modal = new bootstrap.Modal(document.getElementById('viewEvaluationModal'));
    modal.show();
}

/* ============================
   FORMAT CONVERSATION FOR DISPLAY
============================ */

/**
 * Formats the conversation messages into a Markdown string with role labels.
 * @param {Array} conversation - List of conversation messages.
 * @returns {string} - Formatted Markdown string.
 */
function formatConversation(conversation) {
    if (!Array.isArray(conversation)) return "<p class='text-muted'>No conversation data available.</p>";
    let formatted = "";
    conversation.forEach(msg => {
        const role = msg.role.charAt(0).toUpperCase() + msg.role.slice(1); // Capitalize first letter
        const content = escapeHTML(msg.content);
        formatted += `**${role}:**\n${content}\n\n`;
    });
    // Convert the formatted string to HTML using Showdown.js
    const converter = new showdown.Converter();
    return converter.makeHtml(formatted);
}


/* ============================
   WORKFLOW MANAGEMENT FUNCTIONS
============================ */

function copyWorkflow(workflowId) {
    if (confirm("Are you sure you want to copy this workflow?")) {
        postData(`/projects/${projectId}/copy_workflow`, { workflow_id: workflowId })
            .then(data => {
                if (data.status === "workflow_copied") {
                    showAlert("success", "Workflow copied successfully.");
                    window.location.reload();
                } else {
                    showAlert("danger", data.error || "Failed to copy workflow.");
                }
            })
            .catch(error => {
                showAlert("danger", "An error occurred while copying the workflow.");
                console.error("Copy Workflow Error:", error);
            });
    }
}

function deleteWorkflow(workflowId) {
    if (confirm("Are you sure you want to delete this workflow? This action cannot be undone.")) {
        postData(`/projects/${projectId}/delete_workflow`, { workflow_id: workflowId })
            .then(data => {
                if (data.status === "workflow_deleted") {
                    showAlert("success", "Workflow deleted successfully.");
                    window.location.reload();
                } else {
                    showAlert("danger", data.error || "Failed to delete workflow.");
                }
            })
            .catch(error => {
                showAlert("danger", "An error occurred while deleting the workflow.");
                console.error("Delete Workflow Error:", error);
            });
    }
}

/* ============================
   WORKFLOW MANAGEMENT FUNCTIONS WITH DESCRIPTION
============================ */

/**
 * Handles the submission of the Add Workflow form.
 */
function submitAddWorkflow() {
    const form = document.getElementById("addWorkflowForm");
    const workflowNameInput = document.getElementById("workflowName");
    const workflowDescriptionInput = document.getElementById("workflowDescription");
    
    // Reset previous validation states
    form.classList.remove('was-validated');
    
    // Simple form validation
    if (!workflowNameInput.value.trim() || !workflowDescriptionInput.value.trim()) {
        form.classList.add('was-validated');
        showAlert("danger", "Both workflow name and description are required.");
        return;
    }
    
    const workflowName = workflowNameInput.value.trim();
    const workflowDescription = workflowDescriptionInput.value.trim();
    
    // Select the button by its unique ID
    const submitButton = document.getElementById("submitAddWorkflowBtn");
    submitButton.disabled = true;
    submitButton.textContent = "Adding...";
    
    // Send POST request to add the workflow
    postData(`/projects/${projectId}/add_workflow`, { 
        workflow_name: workflowName, 
        workflow_description: workflowDescription 
    })
    .then(data => {
        if (data.status === "workflow_added") {
            showAlert("success", "Workflow created successfully.");
            // Hide the modal
            const addWorkflowModalInstance = bootstrap.Modal.getInstance(document.getElementById('addWorkflowModal'));
            if (addWorkflowModalInstance) addWorkflowModalInstance.hide();
            // Reset the form
            form.reset();
            // Optionally, redirect to the new workflow's detail page
            window.location.href = `/projects/${projectId}/workflow/${data.workflow_id}`;
        } else {
            showAlert("danger", data.error || "Failed to create workflow.");
        }
    })
    .catch(error => {
        showAlert("danger", "An error occurred while creating the workflow.");
        console.error("Add Workflow Error:", error);
    })
    .finally(() => {
        // Re-enable the submit button
        submitButton.disabled = false;
        submitButton.textContent = "Add Workflow";
    });
}


/* ============================
   Function Handling
============================ */


// Initialize CodeMirror and handle function call editor
async function openFunctionSidePanel(stepId, callId = null) {
    const rightPane = document.getElementById("rightPane");
    const dragHandle = document.getElementById("dragHandle");

    rightPane.style.display = "block";
    rightPane.style.flex = "0 0 33.333%"; 
    dragHandle.style.display = "block";

    document.getElementById("functionForm").reset();
    document.getElementById("functionCallId").value = callId || "";
    document.getElementById("functionCallStepId").value = stepId;
    document.getElementById("functionRemoveBtn").style.display = callId ? "inline-block" : "none";

    if (functionCodeEditor) {
        functionCodeEditor.toTextArea(); // Destroy previous instance if exists
        functionCodeEditor = null;
    }

    // Initialize CodeMirror on the functionCode textarea
    const textarea = document.getElementById("functionCode");
    functionCodeEditor = CodeMirror.fromTextArea(textarea, {
        mode: "python",
        theme: "eclipse", // Optional: Choose a theme you like
        lineNumbers: true,
        indentUnit: 4,
        tabSize: 4,
        matchBrackets: true,
        autofocus: true
    });

    if (callId) {
        await loadExistingFunctionData(stepId, callId);
    } else {
        if (functionCodeEditor) {
            functionCodeEditor.setValue("# output_data = {...}");
        }
        document.getElementById("functionTitle").value = "";
        document.getElementById("functionInputVars").value = "{}";
        document.getElementById("functionOutputVar").value = "";
    }
}

async function loadExistingFunctionData(stepId, callId) {
    const workflowData = await fetchData(`/report/${projectId}/${workflowId}`);
    if (!workflowData) return;
    const stepData = workflowData.steps.find(s => s.step_id === stepId);
    if (!stepData) return;
    const fnData = stepData.functions.find(f => f.call_id === callId);
    if (!fnData) return;

    document.getElementById("functionTitle").value = fnData.title || "";
    document.getElementById("functionInputVars").value = JSON.stringify(fnData.input_variables, null, 2);
    document.getElementById("functionOutputVar").value = fnData.output_variable || "";

    if (functionCodeEditor) {
        functionCodeEditor.setValue(fnData.code || "");
    }
}

function closeFunctionSidePanel() {
    const rightPane = document.getElementById("rightPane");
    const dragHandle = document.getElementById("dragHandle");
    const leftPane = document.getElementById("leftPane");

    rightPane.style.display = "none";
    rightPane.style.flex = "0 0 0%";
    dragHandle.style.display = "none";
    leftPane.style.flex = "1 1 100%";

    document.getElementById("functionForm").reset();
    document.getElementById("functionCallId").value = "";
    document.getElementById("functionCallStepId").value = "";
    document.getElementById("functionRemoveBtn").style.display = "none";

    // Clear CodeMirror instance
    if (functionCodeEditor) {
        functionCodeEditor.toTextArea();
        functionCodeEditor = null;
    }
}

async function saveFunctionCall() {
    const callId = document.getElementById("functionCallId").value;
    const stepId = document.getElementById("functionCallStepId").value;
    const title = document.getElementById("functionTitle").value.trim();
    let code = "";
    if (functionCodeEditor) {
        code = functionCodeEditor.getValue();
    } else {
        code = document.getElementById("functionCode").value;
    }
    let inputVars;
    try {
        inputVars = JSON.parse(document.getElementById("functionInputVars").value || "{}");
    } catch (err) {
        showAlert("danger", "Invalid JSON in Input Variables.");
        return;
    }
    const outputVar = document.getElementById("functionOutputVar").value.trim();

    const endpoint = callId ? `/projects/${projectId}/workflow/${workflowId}/edit_function` :
                              `/projects/${projectId}/workflow/${workflowId}/add_function`;
    const payload = { step_id: stepId, title, code, input_variables: inputVars, output_variable: outputVar };
    if (callId) payload.call_id = callId;

    const data = await postData(endpoint, payload);
    if (data.status === (callId ? "function_edited" : "function_added")) {
        showAlert("success", callId ? "Function edited successfully." : "Function added successfully.");
        closeFunctionSidePanel();
        window.location.reload();
    } else {
        showAlert("danger", data.error || "Failed to save function.");
    }
}

async function removeFunctionCall() {
    const callId = document.getElementById("functionCallId").value;
    const stepId = document.getElementById("functionCallStepId").value;
    if (!callId || !stepId) {
        showAlert("danger", "Cannot remove function: missing IDs.");
        return;
    }

    const data = await postData(`/projects/${projectId}/workflow/${workflowId}/remove_function`, { step_id: stepId, call_id: callId });
    if (data.status === "function_removed") {
        showAlert("success", "Function removed successfully.");
        closeFunctionSidePanel();
        window.location.reload();
    } else {
        showAlert("danger", data.error || "Failed to remove function.");
    }
}



// Event listener for the Create Code button
document.addEventListener("DOMContentLoaded", function() {
    const createCodeBtn = document.getElementById("createCodeBtn");
    if (createCodeBtn) {
        createCodeBtn.addEventListener("click", generateWorkflowCode);
    }
});

async function generateWorkflowCode() {
    const createCodeBtn = document.getElementById("createCodeBtn");
    if (createCodeBtn) createCodeBtn.disabled = true;
    
    const generatedCodeContainer = document.getElementById("generatedCodeContainer");
    generatedCodeContainer.innerHTML = `
        <div class="d-flex align-items-center">
            <strong>Generating code...</strong>
            <div class="spinner-border ms-auto" role="status" aria-hidden="true"></div>
        </div>
    `;

    const data = await fetchData(`/generate_code/${projectId}/${workflowId}`);
    if (createCodeBtn) createCodeBtn.disabled = false;

    if (data && data.code) {
        generatedCodeContainer.innerHTML = `
            <h5 class="mt-4">Generated Python Code:</h5>
            <pre><code class="language-python">${escapeHTML(data.code)}</code></pre>
        `;
    } else {
        generatedCodeContainer.innerHTML = "";
        showAlert("danger", data.error || "Failed to generate code.");
    }
}