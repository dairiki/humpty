#include <Python.h>
#include <stdio.h>
#include <string.h>

static PyObject *the_module = NULL;

static PyObject *
get_the_answer(PyObject *self, PyObject *args)
{
  return Py_BuildValue("i", 42);
}


static FILE *
open_data_file(const char * filename)
{
  const char *file = PyModule_GetFilename(the_module);
  FILE *fp = NULL;
  char *path, *tail;

  if (!file)
    return NULL;
  path = PyMem_Malloc(strlen(file) + strlen(filename) + 1);
  if (!path)
    return NULL;
  strcpy(path, file);
  if (!(tail = strrchr(path, '/'))) {
    PyErr_SetString(PyExc_ValueError, "No '/' in __file__");
    goto error;
  }
  strcpy(tail + 1, filename);

  if (!(fp = fopen(path, "r"))) {
    PyErr_SetFromErrno(PyExc_IOError);
    goto error;
  }
 error:
  PyMem_Free(path);
  return fp;
}


static PyObject *
read_the_answer(PyObject *self, PyObject *args)
{
  PyObject *result = NULL;
  FILE *fp = open_data_file("answer.dat");
  int answer;

  if (!fp)
    return NULL;

  if (fscanf(fp, "%d", &answer) == 1) {
    result = Py_BuildValue("i", answer);
  } else {
    Py_INCREF(Py_None);
    result = Py_None;
  }
  fclose(fp);
  return result;
}


static PyMethodDef methods[] = {
  {"get_the_answer", get_the_answer, METH_VARARGS,
   "Get the answer (which is 42.)"},
  {"read_the_answer", read_the_answer, METH_VARARGS,
   "Read integer from answer.data"},
  {NULL, NULL, 0, NULL}
};


#if PY_MAJOR_VERSION >= 3

static struct PyModuleDef moduledef = {
  PyModuleDef_HEAD_INIT,
  "test_ext",
  NULL,
  -1,
  methods
};

PyObject *
PyInit_test_ext(void)
{
  the_module = PyModule_Create(&moduledef);
  return the_module;
}

#else /* python 2 */

PyMODINIT_FUNC
inittest_ext(void)
{
  the_module = Py_InitModule("test_ext", methods);
}

#endif
