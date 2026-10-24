# A document with diagrams

Prose before the diagram.

```mermaid
sequenceDiagram
  %% slarti: attach user user
  %% slarti: attach api api
  actor user
  participant api
  user->>api: uses
```

Generated regions are slartiarch's own output and are never read back:

<!-- slarti:begin diagram:index -->

```mermaid
graph TB
  A --> B
```

<!-- slarti:end diagram:index -->

~~~mermaid
erDiagram
  %% slarti: ignore * the domain model, which the LinkML schema checks
  TASK
~~~

```python
print("not a diagram")
```
