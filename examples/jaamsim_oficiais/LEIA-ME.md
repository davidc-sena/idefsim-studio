# Exemplos do JaamSim convertidos para IDEF-SIM

Modelos convertidos automaticamente dos exemplos oficiais do JaamSim (<https://github.com/jaamsim/jaamsim>, Apache License 2.0, © JaamSim Software Inc. e Ausenco Engineering Canada Inc.), com o importador do IDEF-SIM Studio. São modelos conceituais: o que não tem equivalente em IDEF-SIM está anotado na descrição de cada modelo. A licença original está em `LICENSE-JaamSim.txt`.

Convertidos: 82 · Não convertidos: 9

| Categoria | Exemplo | Observações |
|---|---|---|
| Objetos básicos | DowntimeEntity Example - EntityConveyor | 1 |
| Objetos básicos | DowntimeEntity Example - Server | 1 |
| Objetos básicos | DowntimeEntity Example - with ResourceList | 2 |
| Objetos básicos | EntitlementSelector Example | 3 |
| Objetos básicos | EntitySystem Example | 1 |
| Objetos básicos | EventSchedule Example | 4 |
| Objetos básicos | ExpressionLogger Example - with ValueTraceList | 1 |
| Objetos básicos | ExpressionLogger Example | 1 |
| Objetos básicos | ExpressionThreshold Example - with CloseCondition | 2 |
| Objetos básicos | ExpressionThreshold Example | 2 |
| Objetos básicos | InputValue Example | 1 |
| Objetos básicos | SignalThreshold and EntitySignal Example | 3 |
| Objetos básicos | TimeSeries and TimeSeriesThreshold Example | 2 |
| Objetos básicos | ValueSequence Example | 1 |
| Biblioteca Big Lean | A1-1 Push vs Pull with Kanban-Office | 4 |
| Biblioteca Big Lean | A1-2 Push vs Pull with Kanban-Mfg | 4 |
| Biblioteca Big Lean | A10-1 Cross-Training-Server Farm | 33 |
| Biblioteca Big Lean | A11-1 Load Leveling - Emergency Department | 3 |
| Biblioteca Big Lean | A12-1 Rework-IDEF0 Process Mapping-Lending | 2 |
| Biblioteca Big Lean | A13-1 Quincunx Binomial Simulator | 2 |
| Biblioteca Big Lean | A14-1 Distribution Sandbox | 2 |
| Biblioteca Big Lean | A15-1 Series vs Parallel Approvals | 3 |
| Biblioteca Big Lean | A2-1 Batch vs One Piece Flow with Setup-Office | 22 |
| Biblioteca Big Lean | A2-2 Batch vs One Piece Flow with Setup-Manufacturing | 22 |
| Biblioteca Big Lean | A3-1 Takt Time and Line Balancing-Takt Sign | 4 |
| Biblioteca Big Lean | A3-2 Takt Time and Line Balancing-Gingerbread | 4 |
| Biblioteca Big Lean | A4-1 Variation in a Push System-Office Work | 1 |
| Biblioteca Big Lean | A4-2 Variation in a Push System-Manufacturing | 1 |
| Biblioteca Big Lean | A5-1 Batch vs One Piece Flow with Transport-Office | 19 |
| Biblioteca Big Lean | A6-1 Variation in a Pull System-Office | 3 |
| Biblioteca Big Lean | A6-2 Variation in a Pull System-Manufacturing | 3 |
| Biblioteca Big Lean | A7-1 Shared vs Unshared Queue-Hospital | 33 |
| Biblioteca Big Lean | A8-1 Little's Law Demonstrated-Call Center | 5 |
| Biblioteca Big Lean | A9-1 Kanban Game-Making Robots | 2 |
| Modelos completos | Cafe Model Example | 1 |
| Modelos completos | Decision Loop Example | 2 |
| Modelos completos | Factory Example - 1) with input file | 4 |
| Modelos completos | Factory Example - 10) with maintenance | 5 |
| Modelos completos | Factory Example - 2) with scenarios | 4 |
| Modelos completos | Factory Example - 3) with delays | 2 |
| Modelos completos | Factory Example - 4) with counts | 2 |
| Modelos completos | Factory Example - 5) with bar gauges | 2 |
| Modelos completos | Factory Example - 6) with graph | 2 |
| Modelos completos | Factory Example - 7) with variable arrivals | 5 |
| Modelos completos | Factory Example - 8) with max queue | 5 |
| Modelos completos | Factory Example - 9) with shifts | 5 |
| Modelos completos | Factory Example | 1 |
| Modelos completos | Fill Orders Example - with NextEntity and SelectionCondition | 2 |
| Gráficos | BarGauge Example | 1 |
| Modelos completos | Job Shop Example | 8 |
| Modelos completos | Monthly Totals Example | 2 |
| Distribuições | NonStatExponentialDist Example | 3 |
| Fluxo de processo | AddTo, RemoveFrom, and EntityContainer Example | 4 |
| Fluxo de processo | Assemble Example | 1 |
| Fluxo de processo | Assign Example | 1 |
| Fluxo de processo | Branch Example - select shortest Queue | 2 |
| Fluxo de processo | Branch Example | 1 |
| Fluxo de processo | Duplicate Example | 1 |
| Fluxo de processo | Duplicate and Combine Example - with MatchRequired | 1 |
| Fluxo de processo | Duplicate and Combine Example | 1 |
| Fluxo de processo | EntityConveyor Example - with Accumulating | 2 |
| Fluxo de processo | EntityConveyor Example - with Entities of Different Length | 2 |
| Fluxo de processo | EntityConveyor Example - with ReleaseThresholdList | 2 |
| Fluxo de processo | EntityConveyor Example - with TriggerPointList | 1 |
| Fluxo de processo | EntityConveyor Example - with variable TravelTime | 1 |
| Fluxo de processo | EntityLauncher Example | 1 |
| Fluxo de processo | EntityLogger Example - with TraceEntityStates | 1 |
| Fluxo de processo | EntityLogger Example | 1 |
| Fluxo de processo | EntityProcessor Example - with ReleaseThresholdList | 2 |
| Fluxo de processo | EntityProcessor Example | 1 |
| Fluxo de processo | Pack, Unpack, and EntityContainer Example | 4 |
| Fluxo de processo | Queue Example - with Renege | 0 |
| Fluxo de processo | Seize Example - with Priority | 1 |
| Fluxo de processo | Seize, Release, and Resource Example | 1 |
| Fluxo de processo | Server Example - with ReleaseThresholdList | 2 |
| Fluxo de processo | Server Example - with StateGraphics | 1 |
| Fluxo de processo | Server and Queue Example | 1 |
| Fluxo de processo | SetGraphics Example | 1 |
| Fluxo de processo | Statistics and XYGraph Example | 1 |
| Recursos | ResourceUnit and ResourcePool Example - with FollowAssignment | 1 |
| Recursos | ResourceUnit and ResourcePool Example | 1 |
| Submodelos | Nested SubModel Example | 3 |

## Não convertidos (sem fluxo de entidades)

- `Basic_Objects/FileToHashMap Example.cfg` — O modelo não gera entidades (sem EntityGenerator): não há fluxo de entidades para representar em IDEF-SIM.
- `Basic_Objects/FileToVector and FileToMatrix Example.cfg` — O modelo não gera entidades (sem EntityGenerator): não há fluxo de entidades para representar em IDEF-SIM.
- `Calculation_Objects/Harmonic Oscillator Example.cfg` — O modelo não gera entidades (sem EntityGenerator): não há fluxo de entidades para representar em IDEF-SIM.
- `Calculation_Objects/PIDController Example.cfg` — O modelo não gera entidades (sem EntityGenerator): não há fluxo de entidades para representar em IDEF-SIM.
- `Calculation_Objects/SineWave and SquareWave Example.cfg` — O modelo não gera entidades (sem EntityGenerator): não há fluxo de entidades para representar em IDEF-SIM.
- `Calculation_Objects/UnitDelay Example.cfg` — O modelo não gera entidades (sem EntityGenerator): não há fluxo de entidades para representar em IDEF-SIM.
- `Fluid_Objects/FluidFlow Example.cfg` — O modelo não gera entidades (sem EntityGenerator): não há fluxo de entidades para representar em IDEF-SIM.
- `Graphics_Objects/3D Animation Example.cfg` — O modelo não gera entidades (sem EntityGenerator): não há fluxo de entidades para representar em IDEF-SIM.
- `Graphics_Objects/3D Graphics Example.cfg` — O modelo não gera entidades (sem EntityGenerator): não há fluxo de entidades para representar em IDEF-SIM.
