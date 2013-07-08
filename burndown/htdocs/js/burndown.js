$(document).ready(function(){

  // Expects date as a string in yyyy-mm-dd format. This is then converted
  // to a JS date object in the same yyyy-mm-dd format for the jqPlot library.
  window.dateFormat = function(date){
    split_date = date.split('-');
    // The month is zero indexed hence -1
    var formatted_date = $.datepicker.formatDate('yy-mm-dd', new Date(split_date[0], split_date[1] - 1, split_date[2]));
    return formatted_date
  };

  window.burndownchartdata = new Array();
  for (i in burndowndata) {
    if (i == 'name') {
      var milestone_name = burndowndata['name'];
    }
    else if (i == 'start_date') {
      var milestone_start = burndowndata['start_date'];
    }
    else if (i == 'end_date') {
      var milestone_end = burndowndata['end_date'];
    }
    else if (i == 'total_hours') {
      var total_hours = burndowndata['total_hours'];
    }
    else if (i == 'hours_logged') {
      var hours_logged = burndowndata['hours_logged'];
    }
    else {
      burndownchartdata.push(dateFormat(burndowndata[i]));
    }
  }

  var sortedData = burndownchartdata.sort() // To be chronological

  // Render the jqPlot burn down chart
  var sprint_effort = [[burndowndata['start_date'], total_hours], ['2013-07-25', 10], [burndowndata['end_date'], 0]];
  var team_effort = [['2013-07-25', burndowndata['hours_logged'], ['2013-07-26', 20]]]
  var plot1 = $.jqplot('chart1', [sprint_effort, team_effort], {
    //title: burndowndata['name'],
    axesDefaults: {
      tickRenderer: $.jqplot.CanvasAxisTickRenderer ,
      tickOptions: {
      fontFamily: 'Verdana', // Can't use open sans
      fontSize: '8pt',
        }
    },
    axes: {
      xaxis: {
        renderer:$.jqplot.DateAxisRenderer,
        tickOptions:{formatString: '%d %b'},
        label: 'Days',
        min: burndowndata['start_date'],
        max: burndowndata['end_date'],
      },
      yaxis: {
        label: 'Effort',
        min: 0,
      }
    }, 
    highlighter: {
      show: true, 
      tooltipAxes: 'both',
      sizeAdjust: 7.5,
      fadeTooltip: true,
      tooltipFadeSpeed: 'fast',
      formatString: 'Remaing Effort - %y on %d',
      },
    series:[
            {color:'#5FAB78', label: 'Sprint effort'},
            {label: 'Team effort'},
           ],
    legend: {
      show: true,
      }
  });
});