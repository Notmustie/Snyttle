from graph.workflow import graph


result = graph.invoke({
    "message": "Research the impact of AI on education."
})

print(result["message"])