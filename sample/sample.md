# Database Management Systems — Questions & Answers


## Q1. Major Classes of Parallel Machines and Their Relevance in Parallel Database Systems

Parallel machines are grouped by how processors and memory are linked. This classification directly shapes how data is partitioned, how queries execute, and where the primary costs appear — network time, lock contention, and disk I/O.

### 1. Shared-Memory Machines
- All processors share **one main memory space**
- Any processor can read/write the same data pages
- **Advantages:** Low message-passing cost, simple buffer sharing, joins/sorts can use a shared cache
- **Limitations:** Memory bus saturation, cache conflicts, and lock hot spots become bottlenecks; scales only to a moderate number of CPUs

### 2. Shared-Disk Machines
- Nodes have **separate memories** but share access to the same disks
- Any node can run any part of a query without data movement
- **Advantages:** High availability and easy failover — another node can take over without relocating data
- **Limitations:** Cache coherency traffic and a global lock manager become bottlenecks as the system scales

### 3. Shared-Nothing Machines
- Each node has its **own CPU, memory, and disks**; nodes communicate only over a network
- **Advantages:** Scales well, avoids shared hot spots, operators run where the data lives
- **Limitations:** Data shipping for joins, group-by, and repartition steps is the main cost; good partition keys and careful query planning are essential
- Most large data warehouse systems use this architecture

### 4. Hybrid / Hierarchical Designs
- Combine the above — e.g., small **shared-memory groups** connected in a **shared-nothing cluster**
- Matches modern hardware: many cores/memory per server, many servers per cluster
- Used to get fast local work within a node and scalable growth across nodes, while managing skew, failures, and load balance


## Q2. Eddy Architecture and Reducing Query Response Time in Distributed Systems

**Eddy** is a query engine design that lowers response time by dynamically changing how a query executes while it is running. In large distributed systems, data rates and node load can shift rapidly — a fixed query plan can stall when one operator or site becomes a hot spot.

### How Eddy Works
- Each tuple carries a **small state** marking which operators it has already passed through
- The Eddy core decides **per-tuple** which operator to route it to next
- Routing decisions use **live metrics**: queue size, operator cost, selectivity, and network delay
- When one operator slows or a remote partition is busy, Eddy routes tuples elsewhere or delays expensive work — reducing queue wait time and improving time-to-first-result

### Dynamic Join Ordering
- In distributed joins, the optimal order depends on which streams are heavy and which filters are selective **at that moment**
- Eddy pushes tuples through the most selective filters first, so fewer tuples cross the network and fewer reach costly joins
- This reduces both compute time and data movement — the two key components of response time at scale

### Better Parallel Resource Utilization
- Per-tuple routing spreads work across multiple operator instances, avoiding idle nodes
- Handles **skew** (where one key range is far more common) by steering tuples away from overloaded paths

### Non-Blocking Operators
- Eddy is typically paired with **non-blocking operators** like symmetric hash join
- This allows interleaved execution — output is produced even when some inputs are delayed
- Result: improved time-to-first-answer and steady throughput under changing conditions

**Summary:** Eddy replaces one fixed plan with many small, fast routing decisions guided by live system feedback.


## Q3. Normalization in DBMS — Concept and Normal Forms (1NF to 5NF)

### What is Normalization?
Normalization is a database design method to ensure each fact is **stored exactly once, in the right place**. It decomposes wide tables into smaller, related tables connected by keys.

**Problems it solves:**
- **Update anomaly** — the same value must be changed in many rows
- **Insert anomaly** — a fact cannot be added because other facts are missing
- **Delete anomaly** — removing one row also removes an unrelated needed fact


### First Normal Form (1NF)
**Rule:** Each field holds a **single atomic value** (no lists); rows are unique.

| Violates 1NF | Fixed |
|---|---|
| `Student(StudentID, Name, Courses="Math,CS")` | `Student(StudentID, Name)` + `StudentCourse(StudentID, Course)` |


### Second Normal Form (2NF)
**Rule:** Applies to tables with **composite keys** — every non-key column must depend on the **full key**, not just part of it.

**Example:** `Enrollment(StudentID, CourseID, Grade, StudentName)`
- Key is `(StudentID, CourseID)`
- `StudentName` depends only on `StudentID` → **partial dependency**
- **Fix:** Move `StudentName` to `Student(StudentID, StudentName)`


### Third Normal Form (3NF)
**Rule:** No **transitive dependency** — a non-key column must not depend on another non-key column.

**Example:** `Employee(EmpID, DeptID, DeptName)`
- `DeptName` depends on `DeptID`, not on `EmpID`
- **Fix:** Create `Department(DeptID, DeptName)` and keep `Employee(EmpID, DeptID)`


### Boyce-Codd Normal Form (BCNF)
**Rule:** Stricter than 3NF — every determinant must be a **candidate key**.

**Example:** `Teaching(Teacher, Course, Room)` where `Course → Room`
- `Course` is a determinant but not a candidate key
- **Fix:** Split into `CourseRoom(Course, Room)` and `TeacherCourse(Teacher, Course)`


### Fourth Normal Form (4NF)
**Rule:** No **independent multi-valued facts** in one table.

**Example:** `Person(PersonID, Skill, Language)` — skills and languages are independent
- **Fix:** `PersonSkill(PersonID, Skill)` and `PersonLanguage(PersonID, Language)`


### Fifth Normal Form (5NF)
**Rule:** Eliminates **join dependencies** — a table should not be reconstructible from smaller projections unless those projections represent real constraints.

**Example:** `Supply(Supplier, Part, Project)`
- If only pair-level facts are valid, storing the triple can generate false combinations
- **Fix:** Store `SupplierPart`, `SupplierProject`, and `PartProject` separately


## Q4. Short Notes

### (a) Starburst
Starburst is a data platform built around **Trino**, a distributed SQL query engine. It enables running a single SQL query across multiple data sources without moving the data first — reading from data lakes, object storage, and various databases.

**Key characteristics:**
- Common in **lakehouse** architectures using open formats like Parquet and ORC
- Provides query speed, security, and access control across federated sources
- Supports **connectors** to join data from different systems in one query
- Primary use cases: analytics, reporting, and ad hoc queries at large scale


### (b) Oracle
Oracle is a leading **relational database management system** from Oracle Corporation, widely used in banking, telecom, and other mission-critical industries.

**Key characteristics:**
- Strong **ACID compliance**, backup/recovery, replication, partitioning, and high availability via Real Application Clusters (RAC)
- Stored procedures and triggers through **PL/SQL**
- Runs on most operating systems; scales from small setups to very large enterprise deployments


### (c) DB2
DB2 is IBM's **relational database management system**, available on mainframes and distributed platforms (Linux, Unix, Windows).

**Key characteristics:**
- Known for strong performance, reliability, and support for large business workloads
- Supports SQL, transactions, indexing, and advanced query optimization
- Built-in tools for backup, recovery, and data replication
- Data warehousing features: **compression, partitioning, and parallel processing**
- Preferred in large enterprises where IBM platform stability and long-term support are priorities


## Q5. Database Recovery Management and Backup Techniques

### What is Recovery Management?
Recovery management is the set of methods a database system uses to **restore data to a correct, consistent state after a failure**. Failures can come from power loss, system crashes, software bugs, user errors, or disk damage.

**Two core mechanisms:**
- **Logging** — records each change so the system can redo committed work and undo uncommitted work
- **Backup** — maintains a safe copy of data so it can be restored even if the primary copy is lost


### Backup Techniques

#### 1. Full Backup
- Copies the **entire database**
- Simplest to restore — only one backup file needed
- **Trade-off:** High time and storage cost

#### 2. Partial Backup
- Copies **selected parts** — specific tables or files
- Faster and smaller than a full backup
- Cannot restore the entire database by itself

#### 3. Incremental Backup
- Copies only data **changed since the last backup of any type**
- Small and fast to create
- **Trade-off:** Slower recovery — requires the last full backup plus all incremental backups applied in sequence

#### 4. Differential Backup
- Copies data **changed since the last full backup**
- Grows larger over time
- **Recovery:** Last full backup + latest differential only — faster than incremental

#### 5. Transaction Log Backup
- Saves **log records since the last log backup**
- Enables **point-in-time recovery** — restore to any chosen moment, such as just before an error
- Critical for high-value systems

#### 6. Snapshot Backup
- Captures a **quick image of data at a point in time**
- Very fast to create
- Depends on the storage system; generally does not replace a full backup

**In practice:** Recovery plans combine multiple backup levels to balance cost, recovery time, and risk tolerance.


## Q6. Data Fragmentation in Distributed Databases

### What is Data Fragmentation?
Fragmentation means splitting one logical table into smaller parts and **storing those parts at different sites** in a distributed database. The goal is to place data close to the users and applications that need it most.

**Benefits:**
- Reduced network traffic
- Improved response time
- Supports local processing even when some links are slow

**Constraint:** The original table must always be reconstructible from its fragments, and every row must belong to the correct fragment without ambiguity.


### Types of Fragmentation

#### 1. Horizontal Fragmentation
- Splits a table **by rows** — each fragment holds tuples matching a condition (e.g., `region = 'North'` or `salary > 50000`)
- **Rules:** Fragments must be **complete** (every row appears somewhere) and **disjoint** (no row duplicated, unless replication is intended)
- **Best for:** Queries that filter by a key like branch, country, or time period
- **Advantage:** A site can update its own rows locally without network coordination

#### 2. Vertical Fragmentation
- Splits a table **by columns** — each fragment holds a subset of attributes plus the **primary key** (needed to join fragments back)
- **Example:** `Employee` split into identity data and payroll data
- **Advantage:** Reduces data read/sent when most queries need only some columns; sensitive columns can be placed at more secure sites
- **Trade-off:** Extra joins when a query needs columns from multiple fragments

#### 3. Hybrid (Mixed) Fragmentation
- Combines both — first split by rows, then split each row-fragment by columns (or vice versa)
- Used when workloads have **both location-based and attribute-based access patterns**
- Good design balances local access, join cost, and the ability to reconstruct the full relation