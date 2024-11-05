fl_agent_user_with_tools_first = '''Based on the analysis above, proceed to explore the issue by utilizing relevant tools. Provide specific and well-defined arguments for each tool call, and feel free to use multiple tool calls in a single round if necessary to advance the investigation.'''
fl_agent_user_with_tools_first_without_issue_analysis = '''\n\nProceed to explore the issue by utilizing relevant tools. Provide specific and well-defined arguments for each tool call, and feel free to use multiple tool calls in a single round if necessary to advance the investigation.'''
analyse_result = '''Please analyse the tool calls output.'''
fl_agent_user_with_tools_second = '''Based on your analysis, if you need more information to find out the root cause and precise locations of the bug, construct tool calls to get more information.
Note: 
## Multiple tool calls can be utilized in a single round, but you can only select tools from our tool list and provide arguments as required.
## Please do not repeat calling any tool with the same arguments if it has already been invoked earlier in the conversation. The result from the tool will remain the same each time it is called with identical arguments.
'''
fl_agent_user_with_tools_second_no_review_result = '''If you need more information to find out the root cause and precise locations of the bug, construct tool calls to get more information.
Note: 
## Multiple tool calls can be utilized in a single round, but you can only select tools from our tool list and provide arguments as required.
## Please do not repeat calling any tool with the same arguments if it has already been invoked earlier in the conversation. The result from the tool will remain the same each time it is called with identical arguments.
'''

rules = '''Keep the following rules:
(1) Uncertain Root Cause:\nIf you are unsure of the root cause of the fault or the specific bug location(s) with repair advice, respond using the following JSON format:  \n {{\"root_cause\":\"Unable to locate the bug with the given information.\",\"bug_locations\":[]}}'''+'''
(2) Bug Location Constraints:\nThe fault can only occur in the main code, not in the test code. For example, A bug location should be in the '{proj_main}' directory instead of '{proj_test}'. Also, the fault cannot occur in external libraries.
(3) Code Coverage Requirement:\nThe faulty method must have executed during the test run, with at least one line of code being covered.
(4) Comprehensive Method Inspection:\nDo not provide a bug location unless you have thoroughly examined the content of the method at that location!
(5) Precise Bug Locations:\n Ensure the bug location is precise. For example, if method A calls method B, you have inspected the content of A and suspect method B, you should inspect the content of method B instead of identifying method A as the bug location.
(6) Repair Advice:\nMake sure you have carefully inspected the piece of buggy code at the identified bug location before providing this specific bug location. The repair advice should be based on your thorough inspection and should suggest specific fixes like \"There is a missing null check for the variable \'Tool\'. Add a condition to verify that \'Tool\' is not null before attempting to use it.\" rather than general suggestions like \"check XXX method\" or \"inspect XXX\".'''

output = """
JSON Format for Bug Location:
{{
    \"root_cause\": \"Description of the root cause.\",
    \"bug_locations\": [
        {{
            \"file\": \"path/to/file\",
            \"class\": \"class_name\",
            \"method\": \"method_name\",
            \"repair_advice\": \"specific advice on repairing the bug at this location\"
        }},
        {{
            \"file\": \"path/to/file\",
            \"class\": \"class_name\",
            \"method\": \"method_name\",
            \"repair_advice\": \"specific advice on repairing the bug at this location\"
        }}
        ...
    ]
}}
"""
fl_agent_user_with_tools_upgrade = '''Based on your analysis, if you think you have enough information to locate the bug and provide advice on bug repair, please directly write down the root cause and all the suspicious bug location(s). Each location should have a specific repair recommendation. The bug location should be at least at the method-level, including the file path, the class name, and the buggy method(s) name. If you have known that the method belongs to an inner class, please provide the inner class name as the class name.
Keep your answer in JSON form. Also, if you cannot locate the bug based on the provided information, return a JSON structure indicating this.\n'''+output + "\n" + rules

fl_agent_user_with_tools_upgrade_no_review_result = '''If you think you have enough information to locate the bug and provide advice on bug repair, please directly write down the root cause and all the suspicious bug location(s). Each location should have a specific repair recommendation. The bug location should be at least at the method-level, including the file path, the class name, and the buggy method(s) name. If you have known that the method belongs to an inner class, please provide the inner class name as the class name.
Keep your answer in JSON form. Also, if you cannot locate the bug based on the provided information, return a JSON structure indicating this.\n'''+output + "\n" + rules


final_bug_location_rules = '''Keep the following rules:
(1) Bug Location Constraints:\nThe fault can only occur in the main code, not in the test code. For example, A bug location should be in the '{proj_main}' directory instead of '{proj_test}'. Also, the fault cannot occur in external libraries.
(2) Precise Fault Localization:\nUtilize error information from test cases combined with results from tool analysis to determine the precise fault location. Provide the exact file path, class name, and method name where the bug is located.
'''
fl_agent_final_bug_location = '''Based on your analysis, please write down the root cause and all the suspicious bug locations. Each location should have a specific repair recommendation. The bug location should be at least at the method-level, including the file path, the class name, and the buggy method(s) name. Keep your answer in JSON form.''' + output + final_bug_location_rules

fl_agent_final_bug_location_no_review_result = '''Please write down the root cause and all the suspicious bug locations. Each location should have a specific repair recommendation. The bug location should be at least at the method-level, including the file path, the class name, and the buggy method(s) name. Keep your answer in JSON form.''' + output + final_bug_location_rules

fl_agent_system_with_tools = '''You are a Software Maintenance Engineer working on a large Java repository.
A brief introduction to this repository: {proj_usage}
Your current assignment involves performing fault localization for a specific issue. Details of the failing test case are available, including:
- **Test Path:** The location of the test file.
- **Test Source Code:** The actual code being tested.
- **Test Error Information:** Detailed error messages and outputs from the failure.


**Task**
Determine the root cause of the issue, provide advice for fixing the bug, and document the location(s) of the bug for further analysis.


**Note**
Relative paths for the main code start with `{proj_main}`, and test code starts with `{proj_test}`.
The fault can only occur in the main code, not in the test code. For example, A bug location should be in the '{proj_main}' directory instead of '{proj_test}'. Also, the fault cannot occur in external libraries.
'''


fl_agent_system_with_tools_no_advice = '''You are a Software Maintenance Engineer working on a large Java project.
A brief introduction to this Java project: {proj_usage}
Your current assignment involves performing fault localization for a specific issue. Details of the failing test case are available, including:
- **Test Path:** The location of the test file.
- **Test Source Code:** The actual code being tested.
- **Test Error Information:** Detailed error messages and outputs from the failure.


**Task**
Determine the root cause of the issue and document the location(s) of the bug for further analysis.


**Note**
Relative paths for the main code start with `{proj_main}`, and test code starts with `{proj_test}`.
The fault can only occur in the main code, not in the test code. For example, A bug location should be in the '{proj_main}' directory instead of '{proj_test}'. Also, the fault cannot occur in external libraries.
'''

proj_introduction = {
    "Chart": "This is a Java library for creating a wide variety of highly customizable visual representations of data, such as charts, plots, and maps. It is widely used in applications that require graphical representation of data.",
    "Closure": "This tool is used for making JavaScript download and run faster by minimizing code, checking for syntax errors, optimizing JavaScript, and rewriting and minimizing code.",
    "Lang": "This library provides a host of helper utilities for the Java programming language that are not found in the standard JDK, such as string manipulation, number creation, and date management.",
    "Math": "This project provides a comprehensive suite of lightweight, self-contained mathematics and statistics components addressing the most common problems not available in the Java programming language or Commons Lang.",
    "Time": "This provides a quality replacement for the Java date and time classes. It is widely used for handling date and time in Java applications, offering enhancements for simplicity and efficiency.",
    "Mockito": "This is a mocking framework for Java that allows the creation of mock objects in automated unit tests for the purpose of test-driven development or behavior-driven development.",
    "Collections": "This is a Java library that enhances the Java Collections Framework by providing advanced collection types and utilities, simplifying tasks like list, set, and map manipulation.",
    "Cli": "This is a library for parsing command line options and arguments, providing a simple API for defining options and parsing command line arguments.",
    "Codec": "This is a package of encoding and decoding utilities, including the implementation of some widely used encoders and decoders.",
    "Compress": "This is a library for working with archives and compressed files, providing support for the most common compression and archive formats.",
    "Csv": "This is a library for reading and writing CSV files, providing a simple and efficient API for handling CSV data.",
    "JacksonCore": "This project provides the basic functionality for reading and writing JSON data in Java.",
    "JacksonXml": "This is a library for reading and writing XML data, providing support for XML data manipulation in Java.",
    "Jsoup": "This is a Java library for working with real-world HTML, providing a simple API for extracting and manipulating data, cleaning HTML, and parsing documents.",
    "JxPath": "This library provides an implementation of XPath, a query language for navigating and selecting nodes in XML documents, applied to Java objects. It allows developers to easily traverse and manipulate complex data structures using XPath expressions."

}

error_info_note_Chart = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `\n\tat org.jfree.chart.plot.XYPlot.getDataRange(XYPlot.java:4493)  Collection c = r.getAnnotations();` shows:
`org.jfree.chart.plot.XYPlot.getDataRange`: The method where the error occurred.
`(XYPlot.java:4493)`: The file and line number.
`Collection c = r.getAnnotations();`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''

error_info_note_Closure = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `\n\tat com.google.javascript.jscomp.CommandLineRunnerTest.testSame(CommandLineRunnerTest.java:1159)  testSame(new String[] { original });` shows:
`com.google.javascript.jscomp.CommandLineRunnerTest.testSame`: The method where the error occurred.
`(CommandLineRunnerTest.java:1159)`: The file and line number.
`testSame(new String[] { original });`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''

error_info_note_Lang = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `\n\tat org.apache.commons.lang3.math.NumberUtils.createNumber(NumberUtils.java:474)  return createInteger(str);` shows:
`org.apache.commons.lang3.math.NumberUtils.createNumber`: The method where the error occurred.
`(NumberUtils.java:474)`: The file and line number.
`return createInteger(str);`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''

error_info_note_Math = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `at org.apache.commons.math3.util.MathArrays.linearCombination(MathArrays.java:846)  double prodHighNext = prodHigh[1];` shows:
`org.apache.commons.math3.util.MathArrays.linearCombination`: The method where the error occurred.
`(MathArrays.java:846)`: The file and line number.
`double prodHighNext = prodHigh[1];`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''

error_info_note_Time = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `at org.joda.time.TestPartial_Basics.testWith3(TestPartial_Basics.java:364)  fail();` shows:
`org.joda.time.TestPartial_Basics.testWith3`: The method where the error occurred.
`(TestPartial_Basics.java:364)`: The file and line number.
`fail();`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''

error_info_note_Mockito = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `\n\tat org.mockito.internal.invocation.InvocationMatcherTest.should_capture_varargs_as_vararg(InvocationMatcherTest.java:154)  Assertions.assertThat(m.getAllValues()).containsExactly(\"a\", \"b\");` shows:
`org.mockito.internal.invocation.InvocationMatcherTest.should_capture_varargs_as_vararg`: The method where the error occurred.
`(InvocationMatcherTest.java:154)`: The file and line number.
`Assertions.assertThat(m.getAllValues()).containsExactly(\"a\", \"b\");`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''

error_info_note_Collections = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `\n\tat org.apache.commons.collections4.keyvalue.MultiKeyTest.testEqualsAfterSerializationOfDerivedClass(MultiKeyTest.java:292)  assertEquals(mk.hashCode(), mk2.hashCode());` shows:
`org.apache.commons.collections4.keyvalue.MultiKeyTest.testEqualsAfterSerializationOfDerivedClass`: The method where the error occurred.
`(MultiKeyTest.java:292)`: The file and line number.
`assertEquals(mk.hashCode(), mk2.hashCode());`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''

error_info_note_Cli = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `\n\tat org.apache.commons.cli.Parser.parse(Parser.java:185)  processOption(t, iterator);` shows:
`org.apache.commons.cli.Parser.parse`: The method where the error occurred.
`(Parser.java:185)`: The file and line number.
`processOption(t, iterator);`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''
error_info_note_Codec = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `\n\tat org.apache.commons.codec.binary.Base64OutputStreamTest.testByteByByte(Base64OutputStreamTest.java:142)  assertTrue(\"Streaming base64 encode\", Arrays.equals(output, encoded));` shows:
`org.apache.commons.codec.binary.Base64OutputStreamTest.testByteByByte`: The method where the error occurred.
`(Base64OutputStreamTest.java:142)`: The file and line number.
`assertTrue(\"Streaming base64 encode\", Arrays.equals(output, encoded));`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''

error_info_note_Compress = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `\n\tat org.apache.commons.compress.archivers.tar.TarArchiveOutputStreamTest.testCount(TarArchiveOutputStreamTest.java:55)  assertEquals(f.length(), tarOut.getBytesWritten());` shows:
`org.apache.commons.compress.archivers.tar.TarArchiveOutputStreamTest.testCount`: The method where the error occurred.
`(TarArchiveOutputStreamTest.java:55)`: The file and line number.
`assertEquals(f.length(), tarOut.getBytesWritten());`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''

error_info_note_Csv = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `\n\tat org.apache.commons.csv.CSVRecordTest.testToMapWithShortRecord(CSVRecordTest.java:167)  shortRec.toMap();` shows:
`org.apache.commons.csv.CSVRecordTest.testToMapWithShortRecord`: The method where the error occurred.
`(CSVRecordTest.java:167)`: The file and line number.
`shortRec.toMap();`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''

error_info_note_JacksonCore = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `\n\tat com.fasterxml.jackson.core.json.TestLocation.testOffsetWithInputOffset(TestLocation.java:68)  assertEquals(0L, loc.getByteOffset());` shows:
`com.fasterxml.jackson.core.json.TestLocation.testOffsetWithInputOffset`: The method where the error occurred.
`(TestLocation.java:68)`: The file and line number.
`assertEquals(0L, loc.getByteOffset());`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''


error_info_note_JacksonXml = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `\n\tat com.fasterxml.jackson.dataformat.xml.stream.XmlParserNextXxxTest.testXmlAttributesWithNextTextValue(XmlParserNextXxxTest.java:41)  assertEquals(\"7\", xp.nextTextValue());` shows:
`com.fasterxml.jackson.dataformat.xml.stream.XmlParserNextXxxTest.testXmlAttributesWithNextTextValue`: The method where the error occurred.
`(XmlParserNextXxxTest.java:41)`: The file and line number.
`assertEquals(\"7\", xp.nextTextValue());`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''

error_info_note_Jsoup = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `\n\tat org.jsoup.nodes.DocumentTest.testShiftJisRoundtrip(DocumentTest.java:406)  assertFalse(\"Should not have contained a '?'.\", output.contains(\"?\"));` shows:
`org.jsoup.nodes.DocumentTest.testShiftJisRoundtrip`: The method where the error occurred.
`(DocumentTest.java:406)`: The file and line number.
`assertFalse(\"Should not have contained a '?'.\", output.contains(\"?\"));`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''

error_info_note_JxPath = '''Note: Each stack trace entry in Test Error Information is followed by the corresponding source code. 
For example, the entry `\n\tat org.apache.commons.jxpath.ri.JXPathContextReferenceImpl.getValue(JXPathContextReferenceImpl.java:289)  return getValue(xpath, expression);` shows:
`org.apache.commons.jxpath.ri.JXPathContextReferenceImpl.getValue`: The method where the error occurred.
`(JXPathContextReferenceImpl.java:289)`: The file and line number.
`return getValue(xpath, expression);`: The specific line of code at this location, indicating what was executing when the error was triggered.
'''

error_info_note = {
    "Chart": error_info_note_Chart,
    "Closure": error_info_note_Closure,
    "Lang": error_info_note_Lang,
    "Math": error_info_note_Math,
    "Time": error_info_note_Time,
    "Mockito": error_info_note_Mockito,
    "Collections":error_info_note_Collections,
    "Cli": error_info_note_Cli,
    "Codec":error_info_note_Codec,
    "Compress":error_info_note_Compress,
    "Csv":error_info_note_Csv,
    "JacksonCore":error_info_note_JacksonCore,
    "JacksonXml":error_info_note_JacksonXml,
    "Jsoup":error_info_note_Jsoup,
    "JxPath":error_info_note_JxPath
}


double_ask_output_force = """
JSON Format for More Suspicious Locations:
{
    \"more_suspicious_locations\": [
        {
            \"file\": \"path/to/file\",
            \"class\": \"class_name\",
            \"method\": \"method_name\",
            \"repair_advice\": \"specific advice on repairing the bug at this location\"
        },
        {
            \"file\": \"path/to/file\",
            \"class\": \"class_name\",
            \"method\": \"method_name\",
            \"repair_advice\": \"specific advice on repairing the bug at this location\"
        }
        ...
    ]
}
"""
location_double_ask_force = '''Based on your investigations and reasoning above, please think carefully and write down more suspicious locations closely associated with the bug in JSON form. ''' + double_ask_output_force
sort_form_index_version = '''
JSON Format for Ranked Methods:
{
    \"ranked_methods\": [
        {
            \"index\": index of the method,
            \"level\": 1
        },
        {
            \"index\": index of the method,
            \"level\": 2
        }
        ...
    ]
}
'''

sort_buggy_methods = '''Please rank the methods based on their levels of suspicion. The most suspicious method should be at the top of the list. Level 1 represents the most suspicious method, followed by level 2, and so on. 
Answer this question in JSON form.''' + sort_form_index_version

recheck = '''In a method, the code line annotated with `//**covered**` is the code line that is covered during the execution of the test case.\n In contrast, the code line in a method without this annotation is not covered.\nPlease inspect the code of each location above and answer whether it is really buggy or not. You should give reasons for your judgment. Return your answer in JSON format as follows:
JSON Format for Recheck:
{
    \"recheck\": [
        {
            \"file\": \"path/to/file\",
            \"class\": \"class_name\",
            \"signature\": \"method_signature\",
            \"buggy\": true,
            \"reason\": \"reason for judgment\"
        },
        {
            \"file\": \"path/to/file\",
            \"class\": \"class_name\",
            \"signature\": \"method_signature\",
            \"buggy\": false,
            \"reason\": \"reason for judgment\"
        }
        ...
    ]
}
'''

