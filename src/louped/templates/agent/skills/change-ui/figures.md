# Figures: recipes

Each example is a `view` for `add_view` (or the figure a `derive` script returns). Copy one,
put in your data, then do these steps:

1. Call `preview_view` with the view. Look at the image. If it is wrong, change the view and look
   again. An error tells you which field is wrong.
2. Call `add_view` with the view and a name.
3. Call `ui_show` to show the figure to the person.

Keep all data inline. Give every figure an `about`: one sentence that tells how to read it.

The preview shows a plotly figure before its frames play, and it does not move. It needs Chrome.

## Points in 3D, each point an item

Use `scatter3d`. Put the item keys in `ids`. Then a click on a point opens its item. Use
`items.folder` for the run's item folder. On an experiment's figure, also give `items.run`.

```json
{
  "kind": "plotly",
  "title": "Claims in 3D",
  "about": "Each point is one claim's embedding. Points near each other have similar text.",
  "data": [
    {
      "type": "scatter3d",
      "mode": "markers",
      "x": [0.1, 0.8, 0.4],
      "y": [0.5, 0.2, 0.9],
      "z": [0.3, 0.7, 0.1],
      "ids": ["28", "29", "30"],
      "text": ["28", "29", "30"],
      "marker": { "size": 4 }
    }
  ],
  "items": { "folder": "raw" }
}
```

## Points in 3D over training steps

Put one frame for each step. Each frame has a `name` (the slider shows it) and the new `data`.
`animation` starts the frames when the figure comes into view. `loop` plays them again from the
first frame. `duration_ms` is the time for each frame. Plotly does not move 3D points smoothly
between frames, so keep `transition_ms` at 0 for 3D. Use it for 2D traces such as `scatter`.

```json
{
  "kind": "plotly",
  "title": "Embeddings over training",
  "about": "Each point is one claim. Each frame is one training step.",
  "data": [{ "type": "scatter3d", "mode": "markers", "x": [0, 1, 2], "y": [0, 1, 0], "z": [0, 0, 1] }],
  "frames": [
    { "name": "step 0", "data": [{ "x": [0, 1, 2], "y": [0, 1, 0], "z": [0, 0, 1] }] },
    { "name": "step 100", "data": [{ "x": [0.4, 0.9, 1.5], "y": [0.2, 0.8, 0.3], "z": [0.1, 0.3, 0.8] }] },
    { "name": "step 200", "data": [{ "x": [0.7, 0.8, 1.1], "y": [0.4, 0.6, 0.5], "z": [0.2, 0.5, 0.6] }] }
  ],
  "animation": { "autoplay": true, "loop": true, "duration_ms": 600 }
}
```

## A loss surface that turns

Use `surface`. `z` is a grid: one row for each `y` value, one column for each `x` value.
`orbit` turns the camera around the z axis. It stops when the person drags or zooms the figure.
It works with frames or without them.

```json
{
  "kind": "plotly",
  "title": "Loss surface",
  "about": "Height is the loss at each point of a plane through the weights. The lowest point is the trained model.",
  "data": [
    {
      "type": "surface",
      "x": [-1, 0, 1],
      "y": [-1, 0, 1],
      "z": [[2.1, 1.4, 2.0], [1.3, 0.6, 1.2], [2.2, 1.5, 2.3]]
    }
  ],
  "animation": { "orbit": true }
}
```

When the person's system asks for less motion, the app does not play or turn a figure by itself.
The Play button stays.

## A Vega-Lite chart with a legend you can click

A `point` selection bound to the legend picks a series. The `opacity` condition makes the other
series pale.

```json
{
  "kind": "vega",
  "title": "Loss by run",
  "about": "Click a run in the legend to make the other runs pale. Double-click to show all again.",
  "spec": {
    "data": {
      "values": [
        { "step": 0, "loss": 2.1, "run": "base" },
        { "step": 100, "loss": 1.4, "run": "base" },
        { "step": 0, "loss": 2.0, "run": "steered" },
        { "step": 100, "loss": 1.1, "run": "steered" }
      ]
    },
    "params": [{ "name": "pick", "select": { "type": "point", "fields": ["run"] }, "bind": "legend" }],
    "mark": "line",
    "encoding": {
      "x": { "field": "step", "type": "quantitative" },
      "y": { "field": "loss", "type": "quantitative" },
      "color": { "field": "run", "type": "nominal" },
      "opacity": { "condition": { "param": "pick", "value": 1 }, "value": 0.15 }
    }
  }
}
```

For a brush, use `{ "name": "span", "select": { "type": "interval", "encodings": ["x"] } }`
in `params`. Then a condition on `span` shows the points in the dragged range.

## A Vega-Lite chart that steps with a slider

A param bound to a `range` input makes a slider. A `filter` keeps the rows of the step that the
slider shows. Fix the scale domains, so the axes do not move between steps.

```json
{
  "kind": "vega",
  "title": "Points by training step",
  "about": "Move the slider to see the points at each training step.",
  "spec": {
    "data": {
      "values": [
        { "step": 0, "x": 0.1, "y": 0.2 },
        { "step": 0, "x": 0.3, "y": 0.6 },
        { "step": 100, "x": 0.4, "y": 0.4 },
        { "step": 100, "x": 0.6, "y": 0.7 }
      ]
    },
    "params": [
      { "name": "at", "value": 0, "bind": { "input": "range", "min": 0, "max": 100, "step": 100, "name": "step " } }
    ],
    "transform": [{ "filter": "datum.step == at" }],
    "mark": "point",
    "encoding": {
      "x": { "field": "x", "type": "quantitative", "scale": { "domain": [0, 1] } },
      "y": { "field": "y", "type": "quantitative", "scale": { "domain": [0, 1] } }
    }
  }
}
```
