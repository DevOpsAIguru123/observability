const API_URL = "";

const todoInput = document.getElementById('todo-input');
const addBtn = document.getElementById('add-btn');
const todoList = document.getElementById('todo-list');
const totalCount = document.getElementById('total-count');
const activeCount = document.getElementById('active-count');
const doneCount = document.getElementById('done-count');

// Fetch Todos
async function fetchTodos() {
    try {
        const res = await fetch(`${API_URL}/todos`);
        const todos = await res.json();
        render(todos);
    } catch (err) {
        console.error("Failed to fetch todos", err);
    }
}

// Add Todo
async function addTodo() {
    const title = todoInput.value.trim();
    if (!title) return;

    try {
        await fetch(`${API_URL}/todos`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title })
        });
        todoInput.value = '';
        fetchTodos();
    } catch (err) {
        console.error("Failed to add todo", err);
        alert("Error adding task. Check logs for traces!");
    }
}

// Mark Done
async function markDone(id) {
    try {
        await fetch(`${API_URL}/todos/${id}/done`, { method: 'PUT' });
        fetchTodos();
    } catch (err) {
        console.error("Failed to mark done", err);
    }
}

// Delete Todo
async function deleteTodo(id) {
    if (!confirm('Are you sure?')) return;
    try {
        await fetch(`${API_URL}/todos/${id}`, { method: 'DELETE' });
        fetchTodos();
    } catch (err) {
        console.error("Failed to delete todo", err);
    }
}

// Render
function render(todos) {
    todoList.innerHTML = '';

    // Stats
    totalCount.textContent = todos.length;
    activeCount.textContent = todos.filter(t => !t.done).length;
    doneCount.textContent = todos.filter(t => t.done).length;

    // List - Show newest first
    todos.reverse().forEach(todo => {
        const li = document.createElement('li');
        li.className = `todo-item ${todo.done ? 'done' : ''}`;

        li.innerHTML = `
            <span class="title">${todo.title}</span>
            <div class="actions">
                ${!todo.done ? `<button class="btn-done" onclick="markDone(${todo.id})">✔ Done</button>` : '<span>✓</span>'}
                <button class="btn-delete" onclick="deleteTodo(${todo.id})">✖</button>
            </div>
        `;
        todoList.appendChild(li);
    });
}

// Listeners
addBtn.addEventListener('click', addTodo);
todoInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') addTodo();
});

// Poll every 2 seconds to see simulator updates
setInterval(fetchTodos, 2000);
fetchTodos();
