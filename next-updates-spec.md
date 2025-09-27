# Sidebar Implementation Checklist

**This checklist outlines the tasks required to build the responsive sidebar component in **`<span class="selected">app.tsx</span>`.

### 1. File & Component Setup

* **[ ] Create a new directory: **`<span class="selected">src/components/Sidebar</span>`.
* **[ ] Create the component file: **`<span class="selected">src/components/Sidebar/Sidebar.tsx</span>`.
* **[ ] Create the stylesheet: **`<span class="selected">src/components/Sidebar/Sidebar.css</span>`.
* **[ ] In **`<span class="selected">Sidebar.tsx</span>`, define a new functional component named `<span class="selected">Sidebar</span>`.
* **[ ] Import **`<span class="selected">Sidebar.css</span>` into `<span class="selected">Sidebar.tsx</span>`.
* **[ ] Import and render the **`<span class="selected"><Sidebar /></span>` component within the main layout of `<span class="selected">app.tsx</span>`.

### 2. State Management & Data Structure

* **[ ] In **`<span class="selected">Sidebar.tsx</span>`, import `<span class="selected">useState</span>` from React.
* **[ ] Create a state variable to manage the sidebar's collapsed/expanded state: **`<span class="selected">const [isExpanded, setIsExpanded] = useState(false);</span>`.
* **[ ] Define a data structure (e.g., an array of objects) to hold the navigation links, sections, and icons.**
  ```
  // Example Structure
  const navItems = [
    {
      section: "Workspace",
      items: [
        { name: "Dashboard", icon: <DashboardIcon />, path: "/dashboard" },
        { name: "AI Agents", icon: <AIAgentIcon />, path: "/agents" },
      ]
    },
    {
      section: "Acquisition",
      isCollapsible: true,
      items: [
        { name: "Email Campaigns", icon: <EmailIcon />, path: "/campaigns" },
      ]
    },
    // ... more sections
  ];

  ```

### 3. Component Markup (TSX)

* **[ ] Use a **`<span class="selected"><nav></span>` element as the root container.
* **[ ] Apply a dynamic class to the **`<span class="selected"><nav></span>` container based on the `<span class="selected">isExpanded</span>` state (e.g., `<span class="selected">className={isExpanded ? 'sidebar expanded' : 'sidebar'}</span>`).
* **[ ] Add the header section with the logo and "Acme Workspace" title. The title text should only be visible when **`<span class="selected">isExpanded</span>` is `<span class="selected">true</span>`.
* **[ ] Create a dedicated button or use an existing icon to act as the expand/collapse toggle. Attach an **`<span class="selected">onClick</span>` handler to it that toggles the `<span class="selected">isExpanded</span>` state.
* **[ ] Conditionally render the "Search" input/component so it only appears when **`<span class="selected">isExpanded</span>` is `<span class="selected">true</span>`.
* **[ ] Map over the **`<span class="selected">navItems</span>` data structure to dynamically render the navigation links.
* **[ ] For each link, display its icon.**
* **[ ] Conditionally render the text label for each link so it only appears when **`<span class="selected">isExpanded</span>` is `<span class="selected">true</span>`.

### 4. Styling (CSS)

* **[ ] Style the base **`<span class="selected">.sidebar</span>` class with a fixed narrow width for the collapsed state (e.g., `<span class="selected">width: 80px;</span>`).
* **[ ] Add a **`<span class="selected">transition</span>` property for the `<span class="selected">width</span>` to ensure a smooth animation (e.g., `<span class="selected">transition: width 0.3s ease;</span>`).
* **[ ] Style the **`<span class="selected">.sidebar.expanded</span>` class with a wider width (e.g., `<span class="selected">width: 280px;</span>`).
* **[ ] Use flexbox to align items within the sidebar (for both collapsed and expanded states).**
* **[ ] Hide overflowing text content when the sidebar is collapsed (**`<span class="selected">overflow-x: hidden;</span>`).
* **[ ] Style the individual navigation items, including hover states.**
* **[ ] Create an **`<span class="selected">.active</span>` class to highlight the currently selected navigation link (e.g., with a different background color).

### 5. Routing & Icons

* **[ ] If not already present, install **`<span class="selected">react-router-dom</span>`.
* **[ ] Install a React icon library, such as **`<span class="selected">lucide-react</span>`.
* **[ ] Import the necessary icons and include them in your **`<span class="selected">navItems</span>` data structure.
* **[ ] Wrap each navigation item in a **`<span class="selected"><NavLink></span>` component from `<span class="selected">react-router-dom</span>`.
* **[ ] Use the **`<span class="selected">to</span>` prop on each `<span class="selected"><NavLink></span>` to point to the `<span class="selected">path</span>` defined in your data structure.
* **[ ] The **`<span class="selected">NavLink</span>` will automatically apply an `<span class="selected">active</span>` class, which you can use for styling the active link.
